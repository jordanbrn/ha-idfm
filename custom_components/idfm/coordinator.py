"""Data update coordinators for the IDFM integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from idfm_api import IDFMApi

from .const import (
    BLOCKING_EFFECTS,
    DISRUPTED_EFFECTS,
    DOMAIN,
    SCAN_INTERVAL_DEPARTURES,
    SCAN_INTERVAL_TRAFFIC,
    STATE_BLOCKING,
    STATE_DISRUPTED,
    STATE_INFO,
    STATE_NORMAL,
)

_LOGGER = logging.getLogger(__name__)


def active_disruptions(reports: list, now: datetime | None = None) -> list:
    """Return the reports that have an application period covering now."""
    now = now or datetime.now(timezone.utc)
    active = []
    for report in reports:
        for start, end in report.periods:
            if start.astimezone(timezone.utc) <= now <= end.astimezone(timezone.utc):
                active.append(report)
                break
    return active


def worst_report(reports: list):
    """Return the most severe report (lowest severity value = highest priority)."""
    return sorted(reports, key=lambda r: r.severity)[0] if reports else None


def status_for_effect(effect: str | None) -> str:
    if effect in BLOCKING_EFFECTS:
        return STATE_BLOCKING
    if effect in DISRUPTED_EFFECTS:
        return STATE_DISRUPTED
    return STATE_INFO


class IdfmTrafficCoordinator(DataUpdateCoordinator):
    """Fetches disruption reports for a single line."""

    def __init__(self, hass: HomeAssistant, api: IDFMApi, line_id: str) -> None:
        self.api = api
        self.line_id = line_id
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_traffic_{line_id}",
            update_interval=timedelta(seconds=SCAN_INTERVAL_TRAFFIC),
        )

    async def _async_update_data(self):
        try:
            return await self.api.get_line_reports(self.line_id, exclude_elevator=True)
        except Exception as err:  # noqa: BLE001 - surfaced to the coordinator
            raise UpdateFailed(f"error fetching IDFM line reports: {err}") from err


class IdfmDeparturesCoordinator(DataUpdateCoordinator):
    """Fetches the next departures for a single stop/line/direction."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: IDFMApi,
        stop_id: str,
        line_id: str | None,
        direction: str | None,
        destination: str | None,
    ) -> None:
        self.api = api
        self.stop_id = stop_id
        self.line_id = line_id
        self.direction = direction
        self.destination = destination
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_departures_{stop_id}_{line_id}",
            update_interval=timedelta(seconds=SCAN_INTERVAL_DEPARTURES),
        )

    async def _async_update_data(self):
        try:
            visits = await self.api.get_traffic(
                self.stop_id, self.destination, self.direction, self.line_id
            )
        except Exception as err:  # noqa: BLE001 - surfaced to the coordinator
            raise UpdateFailed(f"error fetching IDFM departures: {err}") from err

        now = datetime.now(timezone.utc)
        departures = []
        for visit in visits:
            if visit.schedule is None or visit.schedule <= now:
                continue
            minutes = max(0, round((visit.schedule - now).total_seconds() / 60))
            departures.append(
                {
                    "destination": visit.destination_name,
                    "direction": visit.direction,
                    "minutes": minutes,
                    "formatted": f"{minutes}min",
                    "time": visit.schedule.isoformat(),
                    "platform": visit.platform,
                    "at_stop": visit.at_stop,
                    "status": visit.status,
                }
            )
        departures.sort(key=lambda d: d["minutes"])
        return departures
