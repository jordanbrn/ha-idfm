"""Serves the bundled Lovelace cards and registers them as Lovelace resources."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

URL_BASE = "/idfm_files"
CARD_FILES = ["idfm-traffic-card.js", "idfm-departures-card.js"]

_registered = False


async def async_register_frontend(hass: HomeAssistant) -> None:
    global _registered
    if _registered:
        return
    _registered = True

    www_dir = str(Path(__file__).parent / "www")

    try:
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(URL_BASE, www_dir, True)]
        )
    except ImportError:
        # Home Assistant < 2024.7 fallback.
        hass.http.register_static_path(URL_BASE, www_dir, True)

    for filename in CARD_FILES:
        add_extra_js_url(hass, f"{URL_BASE}/{filename}")
