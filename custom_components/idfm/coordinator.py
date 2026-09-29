"""Data update coordinators for the IDFM integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from time import monotonic

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from idfm_api import IDFMApi

from .budget import RequestBudget, StatusTrackingSession
from .const import (
    DOMAIN,
    SCAN_INTERVAL_DEPARTURES,
    SCAN_INTERVAL_TRAFFIC,
    STATE_DISRUPTED,
    STATE_INFO,
    STATE_INTERRUPTED,
)

_LOGGER = logging.getLogger(__name__)

# Navitia severity effects (GTFS-RT "Effect") mapped to the sensor state. Anything not
# listed (OTHER_EFFECT, ADDITIONAL_SERVICE, UNKNOWN_EFFECT...) is informational.
EFFECT_STATES = {
    "NO_SERVICE": STATE_INTERRUPTED,
    "REDUCED_SERVICE": STATE_DISRUPTED,
    "SIGNIFICANT_DELAYS": STATE_DISRUPTED,
    "DETOUR": STATE_DISRUPTED,
    "MODIFIED_SERVICE": STATE_DISRUPTED,
    "STOP_MOVED": STATE_DISRUPTED,
}
STATE_RANK = {STATE_INTERRUPTED: 0, STATE_DISRUPTED: 1, STATE_INFO: 2}


def state_for_report(report) -> str:
    return EFFECT_STATES.get(report.effect, STATE_INFO)


def active_reports(reports: list, now: datetime | None = None) -> list:
    """Return the reports applying right now.

    Planned works come with their actual application periods (e.g. every night from
    22:00 to 05:00 for three weeks), so they only count while service is really cut.
    """
    now = now or datetime.now(timezone.utc)
    return [r for r in reports if any(begin <= now <= end for begin, end in r.periods)]


def worst_report(reports: list):
    """Return the most severe report: by state, then by Navitia priority (0 = top)."""
    if not reports:
        return None
    return min(
        reports,
        key=lambda r: (
            STATE_RANK[state_for_report(r)],
            r.severity if r.severity is not None else 99,
        ),
    )


def _last_status(api: IDFMApi) -> int | None:
    session = getattr(api, "_session", None)
    return session.last_status if isinstance(session, StatusTrackingSession) else None


def _rate_limit_headers(api: IDFMApi) -> dict | None:
    """Return the 429 response headers if the last request was rate limited."""
    session = getattr(api, "_session", None)
    if isinstance(session, StatusTrackingSession) and session.last_status == 429:
        return session.last_headers
    return None


class IdfmTrafficCoordinator(DataUpdateCoordinator):
    """Fetches the Navitia disruption reports for a single line."""

    def __init__(
        self, hass: HomeAssistant, api: IDFMApi, budget: RequestBudget, line_id: str
    ) -> None:
        self.api = api
        self.budget = budget
        self.line_id = line_id
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_traffic_{line_id}",
            update_interval=timedelta(seconds=budget.poll_interval(SCAN_INTERVAL_TRAFFIC)),
        )

    async def _async_update_data(self):
        # Every line polls on its own, so the more lines share the token, the slower
        # each one goes (e.g. 5 lines on a 950/day quota: every ~7.5 min).
        self.update_interval = timedelta(
            seconds=self.budget.poll_interval(SCAN_INTERVAL_TRAFFIC)
        )
        if not self.budget.try_acquire():
            if self.data is None:
                raise UpdateFailed("IDFM traffic quota reached")
            return self.data
        try:
            reports = await self.api.get_line_reports(self.line_id)
        except Exception as err:  # noqa: BLE001 - surfaced to the coordinator
            reports, error = None, err
        else:
            error = None

        # idfm_api returns an empty list (i.e. "no disruption") on any HTTP error for
        # Navitia calls, so the status has to be checked here rather than trusted.
        status = _last_status(self.api)
        if status == 429:
            self.budget.report_rate_limited(_rate_limit_headers(self.api))
            if self.data is not None:
                return self.data
            raise UpdateFailed("IDFM traffic rate limited")
        if error is not None:
            raise UpdateFailed(f"error fetching IDFM line reports: {error}") from error
        if status is not None and status != 200:
            raise UpdateFailed(f"error fetching IDFM line reports: HTTP {status}")
        self.budget.report_success()
        return reports


class IdfmDeparturesCoordinator(DataUpdateCoordinator):
    """Fetches the next departures for a single stop/line/direction."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: IDFMApi,
        budget: RequestBudget,
        stop_id: str,
        line_id: str | None,
        directions: list[str],
        destinations: list[str],
    ) -> None:
        self.api = api
        self.budget = budget
        self.stop_id = stop_id
        self.line_id = line_id
        self.directions = directions
        self.destinations = destinations
        self._last_fetch: float | None = None
        self._visits: list | None = None
        # When the timetable was last actually fetched from IDFM (the minutes are
        # recomputed more often than that from the cached timetable).
        self.fetched_at: datetime | None = None
        # No periodic polling by default: it only runs while a dashboard card is
        # actually showing this sensor (see async_set_active / websocket.py), so
        # idle dashboards don't burn the IDFM API quota.
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_departures_{stop_id}_{line_id}",
            update_interval=None,
        )

    @callback
    def async_set_active(self, active: bool) -> None:
        """Start or stop periodic polling."""
        if active == (self.update_interval is not None):
            return
        if not active:
            self.update_interval = None
            self._unschedule_refresh()
            return

        self.update_interval = timedelta(seconds=SCAN_INTERVAL_DEPARTURES)
        stale = (
            self._last_fetch is None
            or monotonic() - self._last_fetch >= SCAN_INTERVAL_DEPARTURES
        )
        if stale:
            # Debounced, so flipping tabs back and forth can't spam the API.
            self.hass.async_create_task(self.async_request_refresh())
        else:
            self._schedule_refresh()

    async def _async_update_data(self):
        if self.budget.try_acquire():
            self._last_fetch = monotonic()
            try:
                # No filter is passed to the API - a stop/line can have more than one
                # direction or destination selected, and the API only supports a
                # single value each, so all visits are fetched and filtered here.
                self._visits = (
                    await self.api.get_traffic(self.stop_id, line_id=self.line_id)
                ) or []
            except Exception as err:  # noqa: BLE001 - surfaced to the coordinator
                if (headers := _rate_limit_headers(self.api)) is None:
                    raise UpdateFailed(f"error fetching IDFM departures: {err}") from err
                self.budget.report_rate_limited(headers)
                if self._visits is None:
                    raise UpdateFailed("IDFM departures rate limited") from err
            else:
                self.fetched_at = datetime.now(timezone.utc)
                self.budget.report_success()
        elif self._visits is None:
            raise UpdateFailed("IDFM departures quota reached")
        # Quota spent: the last fetched timetable is reused, so the minutes keep
        # counting down (and passed departures drop off) without any request.
        visits = self._visits

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
                    "mission": visit.note,
                    "at_stop": visit.at_stop,
                    "status": visit.status,
                }
            )
        departures.sort(key=lambda d: d["minutes"])
        return departures
