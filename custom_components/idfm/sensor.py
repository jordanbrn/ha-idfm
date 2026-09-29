"""Sensor platform for the IDFM integration."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_COLOR,
    ATTR_DEPARTURES,
    ATTR_DESTINATIONS,
    ATTR_DIRECTIONS,
    ATTR_DISRUPTION_COUNT,
    ATTR_FETCHED_AT,
    ATTR_EFFECT,
    ATTR_LINE_ID,
    ATTR_LINE_NAME,
    ATTR_MESSAGE,
    ATTR_MODE,
    ATTR_SEVERITY,
    ATTR_SHORT_NAME,
    ATTR_STOP_NAME,
    ATTR_TEXT_COLOR,
    ATTR_TITLE,
    CONF_DESTINATIONS,
    CONF_DIRECTIONS,
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
    active_reports,
    state_for_report,
    worst_report,
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
        worst = worst_report(active_reports(self.coordinator.data or []))
        if worst is None:
            return STATE_NORMAL
        return state_for_report(worst)

    @property
    def extra_state_attributes(self) -> dict:
        active = active_reports(self.coordinator.data or [])
        worst = worst_report(active)

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
            attrs[ATTR_EFFECT] = worst.effect
            attrs[ATTR_SEVERITY] = worst.type
        else:
            attrs[ATTR_MESSAGE] = "Trafic normal"
            attrs[ATTR_TITLE] = ""
            attrs[ATTR_EFFECT] = None
            attrs[ATTR_SEVERITY] = None

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
        self._line_info: dict = {}

    @property
    def entity_picture(self) -> str | None:
        line_id = self._entry.data.get(CONF_LINE)
        if not line_id:
            return None
        return f"/api/idfm/icon/{line_id}?style=colored&usage=signage_spaces"

    @property
    def native_value(self) -> int | None:
        departures = self.coordinator.data or []
        return departures[0]["minutes"] if departures else None

    @property
    def extra_state_attributes(self) -> dict:
        departures = self.coordinator.data or []
        line_info = self._line_info
        return {
            ATTR_STOP_NAME: self._entry.data[CONF_STOP_NAME],
            ATTR_LINE_NAME: self._entry.data.get(CONF_LINE_NAME),
            ATTR_SHORT_NAME: line_info.get("short_name", self._entry.data.get(CONF_LINE_NAME)),
            ATTR_COLOR: line_info.get("color", "#0064B0"),
            ATTR_TEXT_COLOR: line_info.get("text_color", "#FFFFFF"),
            ATTR_MODE: self._entry.data.get(CONF_MODE),
            ATTR_DIRECTIONS: self._entry.data.get(CONF_DIRECTIONS, []),
            ATTR_DESTINATIONS: self._entry.data.get(CONF_DESTINATIONS, []),
            ATTR_DEPARTURES: _next_per_direction(departures),
            ATTR_FETCHED_AT: (
                self.coordinator.fetched_at.isoformat()
                if self.coordinator.fetched_at
                else None
            ),
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        line_id = self._entry.data.get(CONF_LINE)
        if line_id:
            self._line_info = await LineInfoRepository.get(
                async_get_clientsession(self.hass), line_id
            )
            self.async_write_ha_state()


def _next_per_direction(departures: list[dict], per_direction: int = 10) -> list[dict]:
    """Keep the next few departures of each direction, so the card can group them
    (a plain top 10 could all be in the busier direction)."""
    counts: dict[str, int] = {}
    kept = []
    for departure in departures:
        key = departure["direction"] or departure["destination"] or ""
        if counts.get(key, 0) < per_direction:
            counts[key] = counts.get(key, 0) + 1
            kept.append(departure)
    return kept
