"""Serves the bundled Lovelace cards and registers them as Lovelace resources."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.core import HomeAssistant

from .icon_view import IdfmIconView

_LOGGER = logging.getLogger(__name__)

URL_BASE = "/idfm_files"
CARD_FILES = ["idfm-traffic-card.js", "idfm-departures-card.js"]

# Bump on every change to the card JS files: it's appended as a cache-busting
# query string so browsers can't keep serving a stale cached copy of the URL
# (the static files are otherwise served with a long max-age).
CARD_VERSION = "2"

_registered = False


async def async_register_frontend(hass: HomeAssistant) -> None:
    global _registered
    if _registered:
        return

    www_dir = str(Path(__file__).parent / "www")

    try:
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(URL_BASE, www_dir, False)]
        )
    except ImportError:
        # Home Assistant < 2024.7 fallback.
        hass.http.register_static_path(URL_BASE, www_dir, False)

    for filename in CARD_FILES:
        add_extra_js_url(hass, f"{URL_BASE}/{filename}?v={CARD_VERSION}")

    hass.http.register_view(IdfmIconView(hass))

    # Only mark done once every step above actually succeeded, so a failure
    # gets retried on the next entry setup / HA restart instead of being
    # silently stuck forever.
    _registered = True
