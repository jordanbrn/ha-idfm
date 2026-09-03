"""Sensor platform for the IDFM integration."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_CHANNEL,
    ATTR_COLOR,
    ATTR_DEPARTURES,
    ATTR_DESTINATION,
    ATTR_DIRECTION,
    ATTR_DISRUPTION_COUNT,
    ATTR_LINE_ID,
    ATTR_LINE_NAME,
    ATTR_MESSAGE,
    ATTR_MODE,
    ATTR_SHORT_NAME,
    ATTR_STOP_NAME,
    ATTR_TEXT_COLOR,
    ATTR_TITLE,
    CONF_DESTINATION,
    CONF_DIRECTION,
    CONF_KIND,
    CONF_LINE,
    CONF_LINE_NAME,
    CONF_MODE,
    CONF_STOP_NAME,
    DOMAIN,
    KIND_DEPARTURES,
    KIND_TRAFFIC,
    MODE_ICONS,
    STATE_NORMAL,
)
from .coordinator import (
    IdfmDeparturesCoordinator,
    IdfmTrafficCoordinator,
    active_messages,
    status_for_channel,
    worst_message,
)
from .lines import LineInfoRepository


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]

    if entry.data[CONF_KIND] == KIND_TRAFFIC:
        async_add_entities([IdfmTrafficSensor(coordinator, entry)])
    elif entry.data[CONF_KIND] == KIND_DEPARTURES:
        async_add_entities([IdfmDeparturesSensor(coordinator, entry)])


class IdfmTrafficSensor(CoordinatorEntity[IdfmTrafficCoordinator], SensorEntity):
    """Traffic status for a single IDFM line."""

    _attr_has_entity_name = False

    def __init__(self, coordinator: IdfmTrafficCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = entry.entry_id
        self._attr_name = entry.data[CONF_LINE_NAME]
        self._attr_icon = MODE_ICONS.get(entry.data.get(CONF_MODE), "mdi:train")
        self._line_info: dict = {}

    @property
    def entity_picture(self) -> str:
        line_id = self._entry.data[CONF_LINE]
        return f"/api/idfm/icon/{line_id}?style=colored&usage=signage_spaces"

    @property
    def native_value(self) -> str:
        active = active_messages(self.coordinator.data or [])
        if not active:
            return STATE_NORMAL
        return status_for_channel(worst_message(active).type)

    @property
    def extra_state_attributes(self) -> dict:
        active = active_messages(self.coordinator.data or [])
        worst = worst_message(active)

        line_id = self._entry.data[CONF_LINE]
        line_info = self._line_info

        attrs = {
            ATTR_LINE_ID: line_id,
            ATTR_LINE_NAME: self._entry.data[CONF_LINE_NAME],
            ATTR_MODE: self._entry.data.get(CONF_MODE),
            ATTR_SHORT_NAME: line_info.get("short_name", self._entry.data[CONF_LINE_NAME]),
            ATTR_COLOR: line_info.get("color", "#0064B0"),
            ATTR_TEXT_COLOR: line_info.get("text_color", "#FFFFFF"),
            ATTR_DISRUPTION_COUNT: len(active),
        }

        if worst is not None:
            attrs[ATTR_MESSAGE] = worst.message or worst.name
            attrs[ATTR_TITLE] = worst.name
            attrs[ATTR_CHANNEL] = worst.type
        else:
            attrs[ATTR_MESSAGE] = "Trafic normal"
            attrs[ATTR_TITLE] = ""
            attrs[ATTR_CHANNEL] = None

        return attrs

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._line_info = await LineInfoRepository.get(
            async_get_clientsession(self.hass), self._entry.data[CONF_LINE]
        )
        self.async_write_ha_state()


class IdfmDeparturesSensor(CoordinatorEntity[IdfmDeparturesCoordinator], SensorEntity):
    """Next departures for a single IDFM stop."""

    _attr_has_entity_name = False
    _attr_native_unit_of_measurement = "min"

    def __init__(self, coordinator: IdfmDeparturesCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = entry.entry_id
        self._attr_name = entry.title
        self._attr_icon = MODE_ICONS.get(entry.data.get(CONF_MODE), "mdi:train")

    @property
    def native_value(self) -> int | None:
        departures = self.coordinator.data or []
        return departures[0]["minutes"] if departures else None

    @property
    def extra_state_attributes(self) -> dict:
        departures = self.coordinator.data or []
        return {
            ATTR_STOP_NAME: self._entry.data[CONF_STOP_NAME],
            ATTR_LINE_NAME: self._entry.data.get(CONF_LINE_NAME),
            ATTR_DIRECTION: self._entry.data.get(CONF_DIRECTION),
            ATTR_DESTINATION: self._entry.data.get(CONF_DESTINATION),
            ATTR_DEPARTURES: departures[:3],
        }
