"""Client-side PRIM quota tracking, so the integration never exceeds its daily quota."""
from __future__ import annotations

import asyncio
import hashlib
import logging
from collections import deque
from time import monotonic, time

from homeassistant.components import persistent_notification
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# PRIM quotas are per token and per API, over a day. Counting over a rolling 24h
# window keeps us under the limit whatever time of day PRIM resets its counter.
WINDOW = 24 * 3600
STORAGE_VERSION = 1
SAVE_DELAY = 60
# After PRIM itself answers 429, stop calling it for a while instead of hammering it,
# doubling the pause on each consecutive 429.
BACKOFF_MIN = 60
BACKOFF_MAX = 15 * 60
# PRIM also rate-limits bursts (e.g. every line refreshing at once on HA startup), so
# requests on a token are sent one at a time, this many seconds apart at least.
MIN_REQUEST_SPACING = 1.0

_BUDGETS_KEY = f"{DOMAIN}_budgets"
_LOCK_KEY = f"{DOMAIN}_budgets_lock"
_THROTTLES_KEY = f"{DOMAIN}_throttles"


class RequestBudget:
    """Rolling 24h request counter for one PRIM API on one token."""

    def __init__(self, hass: HomeAssistant, key: str, api: str, limit: int) -> None:
        self.hass = hass
        self.api = api
        self.limit = limit
        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.budget.{key}.{api}")
        self._calls: deque[float] = deque()
        self._warned = False
        self._paused_until = 0.0
        self._backoff = 0
        # Entries polling on a fixed interval through this budget (traffic lines).
        self.pollers: set[str] = set()
        self._quota_notification_id = f"{DOMAIN}_quota_{key}_{api}"
        self._rate_limit_notification_id = f"{DOMAIN}_rate_limited_{key}_{api}"

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        cutoff = time() - WINDOW
        self._calls = deque(t for t in data.get("calls", []) if t > cutoff)

    def _prune(self) -> None:
        cutoff = time() - WINDOW
        while self._calls and self._calls[0] <= cutoff:
            self._calls.popleft()

    @property
    def used(self) -> int:
        self._prune()
        return len(self._calls)

    def poll_interval(self, base: int) -> int:
        """Polling interval keeping every poller on this budget within the quota."""
        return max(base, -(-len(self.pollers) * WINDOW // self.limit))

    @callback
    def try_acquire(self) -> bool:
        """Record a request and return True, or return False if the quota is spent."""
        if time() < self._paused_until:
            return False
        if self.used >= self.limit:
            if not self._warned:
                _LOGGER.warning(
                    "IDFM %s quota reached (%s requests in the last 24h): pausing "
                    "requests until it frees up, last known data is kept",
                    self.api,
                    self.limit,
                )
                resume = dt_util.as_local(
                    dt_util.utc_from_timestamp(self._calls[0] + WINDOW)
                )
                persistent_notification.async_create(
                    self.hass,
                    f"Le quota de {self.limit} requêtes `{self.api}` sur 24h est "
                    "atteint. Les requêtes vers IDFM sont suspendues (les dernières "
                    "données restent affichées) et reprendront progressivement à "
                    f"partir de {resume:%H:%M}.\n\n"
                    "Pour un quota plus élevé : « Ma consommation API » sur le "
                    "portail PRIM, puis relever `QUOTA_*` dans `const.py`.",
                    title="IDFM : quota atteint",
                    notification_id=self._quota_notification_id,
                )
                self._warned = True
            return False
        if self._warned:
            persistent_notification.async_dismiss(self.hass, self._quota_notification_id)
            self._warned = False
        self._calls.append(time())
        # Persisted so HA restarts don't reset the count (Store also flushes on shutdown).
        self._store.async_delay_save(lambda: {"calls": list(self._calls)}, SAVE_DELAY)
        return True

    @callback
    def report_rate_limited(self, headers: dict | None = None) -> None:
        """PRIM answered 429: back off and tell the user."""
        first = self._backoff == 0
        self._backoff = min(BACKOFF_MAX, max(BACKOFF_MIN, self._backoff * 2))
        self._paused_until = time() + self._backoff
        # Rate-limit / quota headers, to find out which PRIM limit was hit.
        limit_headers = {
            k: v
            for k, v in (headers or {}).items()
            if "limit" in k.lower() or "quota" in k.lower() or k.lower() == "retry-after"
        }
        _LOGGER.warning(
            "IDFM refused a %s request (HTTP 429), retrying in %s s - headers: %s",
            self.api,
            self._backoff,
            limit_headers,
        )
        if not first:
            return
        persistent_notification.async_create(
            self.hass,
            f"IDFM a refusé une requête `{self.api}` (HTTP 429, trop de requêtes). "
            "Le quota journalier PRIM de ce token est probablement épuisé (requêtes "
            "faites avant la mise à jour de l'intégration, ou token utilisé "
            f"ailleurs) : l'intégration n'en compte que {self.used} sur 24h depuis "
            "qu'elle les suit.\n\n"
            "Les dernières données restent affichées, nouvel essai dans "
            f"{BACKOFF_MIN // 60} min puis de plus en plus espacé (jusqu'à "
            f"{BACKOFF_MAX // 60} min). La consommation réelle est visible dans "
            "« Ma consommation API » sur le portail PRIM.",
            title="IDFM : limite de requêtes",
            notification_id=self._rate_limit_notification_id,
        )

    @callback
    def report_success(self) -> None:
        if self._backoff:
            self._backoff = 0
            self._paused_until = 0.0
            persistent_notification.async_dismiss(
                self.hass, self._rate_limit_notification_id
            )


class RequestThrottle:
    """Sends a token's requests one at a time, MIN_REQUEST_SPACING apart."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def wait(self) -> None:
        async with self._lock:
            delay = self._last + MIN_REQUEST_SPACING - monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            self._last = monotonic()


class StatusTrackingSession:
    """Wraps the aiohttp session to throttle requests and expose the last status.

    idfm_api swallows the status code of failed responses, so a 429 would otherwise
    be indistinguishable from any other error.
    """

    def __init__(self, session, throttle: RequestThrottle) -> None:
        self._session = session
        self._throttle = throttle
        self.last_status: int | None = None
        self.last_headers: dict = {}

    async def get(self, *args, **kwargs):
        self.last_status = None
        self.last_headers = {}
        await self._throttle.wait()
        response = await self._session.get(*args, **kwargs)
        self.last_status = response.status
        self.last_headers = dict(response.headers)
        return response


@callback
def async_get_session(hass: HomeAssistant, session, token: str) -> StatusTrackingSession:
    """Return a session wrapper sharing the throttle of every entry on this token."""
    throttles: dict[str, RequestThrottle] = hass.data.setdefault(_THROTTLES_KEY, {})
    throttle = throttles.setdefault(_token_key(token), RequestThrottle())
    return StatusTrackingSession(session, throttle)


def _token_key(token: str) -> str:
    # Hash the token so it never ends up in a storage file name.
    return hashlib.sha256(token.encode()).hexdigest()[:12]


async def async_get_budget(
    hass: HomeAssistant, token: str, api: str, limit: int
) -> RequestBudget:
    """Return the budget shared by every entry using this token for this API."""
    key = _token_key(token)
    budgets: dict[str, RequestBudget] = hass.data.setdefault(_BUDGETS_KEY, {})
    lock: asyncio.Lock = hass.data.setdefault(_LOCK_KEY, asyncio.Lock())
    async with lock:
        budget = budgets.get(f"{key}.{api}")
        if budget is None:
            budget = RequestBudget(hass, key, api, limit)
            await budget.async_load()
            budgets[f"{key}.{api}"] = budget
    return budget
