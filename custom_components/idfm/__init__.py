"""The IDFM (Ile-de-France Mobilités) integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from idfm_api import IDFMApi

from .budget import async_get_budget, async_get_session
from .const import (
    API_LINE_REPORTS,
    API_STOP_MONITORING,
    CONF_DESTINATIONS,
    CONF_DIRECTIONS,
    CONF_KIND,
    CONF_LINE,
    CONF_STOP,
    CONF_TOKEN,
    DOMAIN,
    KIND_DEPARTURES,
    KIND_TRAFFIC,
    PLATFORMS,
    QUOTA_LINE_REPORTS,
    QUOTA_STOP_MONITORING,
)
from .coordinator import IdfmDeparturesCoordinator, IdfmTrafficCoordinator
from .frontend import async_register_frontend
from .lovelace_resources import async_ensure_lovelace_resources
from .websocket import async_has_watchers, async_register_websocket

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    session = async_get_clientsession(hass)
    token = entry.data[CONF_TOKEN]
    api = IDFMApi(async_get_session(hass, session, token), token)

    kind = entry.data[CONF_KIND]
    if kind == KIND_TRAFFIC:
        budget = await async_get_budget(
            hass, token, API_LINE_REPORTS, QUOTA_LINE_REPORTS
        )
        budget.pollers.add(entry.entry_id)
        entry.async_on_unload(lambda: budget.pollers.discard(entry.entry_id))
        coordinator = IdfmTrafficCoordinator(hass, api, budget, entry.data[CONF_LINE])
    elif kind == KIND_DEPARTURES:
        budget = await async_get_budget(
            hass, token, API_STOP_MONITORING, QUOTA_STOP_MONITORING
        )
        coordinator = IdfmDeparturesCoordinator(
            hass,
            api,
            budget,
            entry.data[CONF_STOP],
            entry.data.get(CONF_LINE),
            entry.data.get(CONF_DIRECTIONS, []),
            entry.data.get(CONF_DESTINATIONS, []),
        )
    else:
        _LOGGER.error("unknown IDFM entry kind: %s", kind)
        return False

    async_register_websocket(hass)

    hass.data[DOMAIN][entry.entry_id] = coordinator
    if kind == KIND_DEPARTURES:
        # No fetch at startup: departures are only fetched once a card shows them
        # (a card may already be subscribed, e.g. across an entry reload), so HA
        # restarts don't eat into the stop-monitoring quota.
        coordinator.async_set_active(async_has_watchers(hass, entry.entry_id))
    else:
        try:
            await coordinator.async_config_entry_first_refresh()
        except Exception:
            hass.data[DOMAIN].pop(entry.entry_id, None)
            raise

    try:
        await async_register_frontend(hass)
        await async_ensure_lovelace_resources(hass)
    except Exception:  # noqa: BLE001 - the cards are a bonus, sensors must not fail
        _LOGGER.exception("failed to register IDFM Lovelace cards")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
