"""Websocket API letting the departures card turn polling on only while it's visible."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .coordinator import IdfmDeparturesCoordinator

# entry_id -> number of open card subscriptions. Kept outside the coordinator so
# it survives an entry reload (the card's subscription stays open across it).
WATCHERS_KEY = f"{DOMAIN}_watchers"
_REGISTERED_KEY = f"{DOMAIN}_websocket_registered"


@callback
def async_register_websocket(hass: HomeAssistant) -> None:
    if hass.data.get(_REGISTERED_KEY):
        return
    hass.data[_REGISTERED_KEY] = True
    hass.data.setdefault(WATCHERS_KEY, {})
    websocket_api.async_register_command(hass, ws_subscribe_departures)


@callback
def async_has_watchers(hass: HomeAssistant, entry_id: str) -> bool:
    return hass.data.get(WATCHERS_KEY, {}).get(entry_id, 0) > 0


@callback
def _set_active(hass: HomeAssistant, entry_id: str) -> None:
    coordinator = hass.data.get(DOMAIN, {}).get(entry_id)
    if isinstance(coordinator, IdfmDeparturesCoordinator):
        coordinator.async_set_active(async_has_watchers(hass, entry_id))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "idfm/departures/subscribe",
        vol.Required("entity_id"): cv.entity_id,
    }
)
@callback
def ws_subscribe_departures(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict
) -> None:
    """Keep a departures sensor polling for as long as this subscription is open."""
    entity = er.async_get(hass).async_get(msg["entity_id"])
    if entity is None or entity.platform != DOMAIN or entity.config_entry_id is None:
        connection.send_error(msg["id"], "not_found", "not an IDFM departures sensor")
        return

    entry_id = entity.config_entry_id
    watchers = hass.data[WATCHERS_KEY]
    watchers[entry_id] = watchers.get(entry_id, 0) + 1
    _set_active(hass, entry_id)

    @callback
    def unsubscribe() -> None:
        watchers[entry_id] = max(0, watchers.get(entry_id, 0) - 1)
        if not watchers[entry_id]:
            watchers.pop(entry_id)
        _set_active(hass, entry_id)

    # Called on explicit unsubscribe and when the websocket connection closes.
    connection.subscriptions[msg["id"]] = unsubscribe
    connection.send_result(msg["id"])
