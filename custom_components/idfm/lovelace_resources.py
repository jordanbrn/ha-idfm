"""Auto-registers the bundled Lovelace cards as dashboard resources.

Mirrors what HACS does for frontend repos: write directly into Lovelace's own
resource storage collection so the cards "just work" after installing the
integration, with no manual step in Settings > Dashboards > Resources. This is
the same storage a manually-added resource ends up in - we're just doing it
in Python instead of through the UI.
"""
from __future__ import annotations

import logging

from homeassistant.const import CONF_ID, CONF_URL
from homeassistant.core import HomeAssistant

from .frontend import CARD_FILES, CARD_VERSION, URL_BASE

_LOGGER = logging.getLogger(__name__)


async def async_ensure_lovelace_resources(hass: HomeAssistant) -> None:
    """Create or update our Lovelace resource entries, without touching others."""
    try:
        from homeassistant.components.lovelace.const import (
            CONF_RESOURCE_TYPE_WS,
            LOVELACE_DATA,
        )
        from homeassistant.components.lovelace.resources import (
            ResourceStorageCollection,
        )
    except ImportError:
        _LOGGER.debug("Lovelace resources API unavailable, skipping auto-registration")
        return

    lovelace_data = hass.data.get(LOVELACE_DATA)
    if lovelace_data is None:
        _LOGGER.debug("Lovelace not set up yet, skipping resource auto-registration")
        return

    resources = lovelace_data.resources
    if not isinstance(resources, ResourceStorageCollection):
        # Dashboards in YAML mode manage resources via configuration.yaml only;
        # there is nothing we can safely write to.
        _LOGGER.debug("Lovelace resources are in YAML mode, add the cards manually")
        return

    # async_get_info() is the lazy-load-safe entry point: it forces existing
    # resources to be read from disk before we ever call create/update, so we
    # can't clobber what's already there.
    await resources.async_get_info()
    existing = list(resources.async_items() or [])

    for filename in CARD_FILES:
        base_path = f"{URL_BASE}/{filename}"
        target_url = f"{base_path}?v={CARD_VERSION}"

        matches = [item for item in existing if item[CONF_URL].split("?", 1)[0] == base_path]
        current = next((item for item in matches if item[CONF_URL] == target_url), None)
        if current is not None:
            continue

        if matches:
            # An older version of this resource exists: update it in place
            # instead of creating a duplicate entry.
            await resources.async_update_item(matches[0][CONF_ID], {CONF_URL: target_url})
        else:
            await resources.async_create_item(
                {CONF_RESOURCE_TYPE_WS: "module", CONF_URL: target_url}
            )
