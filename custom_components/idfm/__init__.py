"""The IDFM (Ile-de-France Mobilités) integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from idfm_api import IDFMApi

from .const import (
    CONF_DESTINATION,
    CONF_DIRECTION,
    CONF_KIND,
    CONF_LINE,
    CONF_STOP,
    CONF_TOKEN,
    DOMAIN,
    KIND_DEPARTURES,
    KIND_TRAFFIC,
    PLATFORMS,
)
from .coordinator import IdfmDeparturesCoordinator, IdfmTrafficCoordinator
from .frontend import async_register_frontend
from .lovelace_resources import async_ensure_lovelace_resources

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    session = async_get_clientsession(hass)
    api = IDFMApi(session, entry.data[CONF_TOKEN])

    kind = entry.data[CONF_KIND]
    if kind == KIND_TRAFFIC:
        coordinator = IdfmTrafficCoordinator(hass, api, entry.data[CONF_LINE])
    elif kind == KIND_DEPARTURES:
        coordinator = IdfmDeparturesCoordinator(
            hass,
            api,
            entry.data[CONF_STOP],
            entry.data.get(CONF_LINE),
            entry.data.get(CONF_DIRECTION),
            entry.data.get(CONF_DESTINATION),
        )
    else:
        _LOGGER.error("unknown IDFM entry kind: %s", kind)
        return False

    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

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
