"""Data update coordinators for the IDFM integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from idfm_api import IDFMApi

from .const import (
    DOMAIN,
    SCAN_INTERVAL_DEPARTURES,
    SCAN_INTERVAL_TRAFFIC,
    STATE_DISRUPTED,
    STATE_INFO,
    STATE_NORMAL,
)

_LOGGER = logging.getLogger(__name__)

# InfoChannelRef values seen on the IDFM general-message feed. Only "Perturbation" is
# an actual ongoing incident; "Information" is mostly advance notice for works spanning
# weeks (not "current state"), and "Commercial" is marketing - both are ignored.
ALLOWED_CHANNELS = {"Perturbation"}
CHANNEL_SEVERITY = {"Perturbation": 0, "Information": 1}

# IDFM tags multi-week planned-works campaigns as "Perturbation" too (they do genuinely
# cut service, just only during certain hours each day), which a plain validity-window
# check can't tell apart from a real ongoing incident. A live incident's window is a few
# hours at most, so anything wider is treated as an advance notice, not current state.
MAX_LIVE_DURATION = timedelta(hours=24)


def active_messages(messages: list, now: datetime | None = None) -> list:
    """Return the currently-active service disruptions (matches station screens)."""
    now = now or datetime.now(timezone.utc)
    active = []
    for msg in messages:
        if msg.type not in ALLOWED_CHANNELS:
            continue
        start = msg.start_time.astimezone(timezone.utc)
        end = msg.end_time.astimezone(timezone.utc)
        if not (start <= now <= end):
            continue
        if end - start > MAX_LIVE_DURATION:
            continue
        active.append(msg)
    return active


def worst_message(messages: list):
    """Return the most relevant message: perturbations first, then most recent."""
    if not messages:
        return None
    return sorted(
        messages,
        key=lambda m: (CHANNEL_SEVERITY.get(m.type, 1), -m.start_time.timestamp()),
    )[0]


def status_for_channel(channel: str | None) -> str:
    if channel == "Perturbation":
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
            return await self.api.get_infos(self.line_id)
        except Exception as err:  # noqa: BLE001 - surfaced to the coordinator
            raise UpdateFailed(f"error fetching IDFM traffic messages: {err}") from err


class IdfmDeparturesCoordinator(DataUpdateCoordinator):
    """Fetches the next departures for a single stop/line/direction."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: IDFMApi,
        stop_id: str,
        line_id: str | None,
        directions: list[str],
        destinations: list[str],
    ) -> None:
        self.api = api
        self.stop_id = stop_id
        self.line_id = line_id
        self.directions = directions
        self.destinations = destinations
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_departures_{stop_id}_{line_id}",
            update_interval=timedelta(seconds=SCAN_INTERVAL_DEPARTURES),
        )

    async def _async_update_data(self):
        try:
            # No filter is passed to the API - a stop/line can have more than one
            # direction or destination selected, and the API only supports a single
            # value each, so all visits are fetched and filtered here instead.
            visits = await self.api.get_traffic(self.stop_id, line_id=self.line_id)
        except Exception as err:  # noqa: BLE001 - surfaced to the coordinator
            raise UpdateFailed(f"error fetching IDFM departures: {err}") from err

        has_filters = bool(self.directions or self.destinations)
        now = datetime.now(timezone.utc)
        departures = []
        for visit in visits:
            if visit.schedule is None or visit.schedule <= now:
                continue
            if has_filters and (
                visit.direction not in self.directions
                and visit.destination_name not in self.destinations
            ):
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
