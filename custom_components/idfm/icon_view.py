"""Proxies the official IDFM line pictograms so the PRIM API key stays server-side.

Browsers can't attach a custom "apiKey" header to a plain <img> tag, so the
Lovelace cards point at this local endpoint instead of calling PRIM directly.
"""
from __future__ import annotations

import logging

from aiohttp import ClientError, web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_TOKEN, DOMAIN

_LOGGER = logging.getLogger(__name__)

ICON_URL = "https://prim.iledefrance-mobilites.fr/marketplace/ilico/getIcon/{line_id}"

# Pictograms are static artwork, so cache the bytes for the lifetime of the process.
_cache: dict[str, tuple[bytes, str]] = {}


class IdfmIconView(HomeAssistantView):
    """Serves /api/idfm/icon/<line_id>?style=colored&usage=signage_spaces."""

    url = "/api/idfm/icon/{line_id}"
    name = "api:idfm:icon"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(self, request: web.Request, line_id: str) -> web.Response:
        style = request.query.get("style", "colored")
        usage = request.query.get("usage", "signage_spaces")
        cache_key = f"{line_id}:{usage}:{style}"

        cached = _cache.get(cache_key)
        if cached is not None:
            body, content_type = cached
            return web.Response(body=body, content_type=content_type)

        token = self._get_token()
        if token is None:
            return web.Response(status=404)

        session = async_get_clientsession(self.hass)
        try:
            resp = await session.get(
                ICON_URL.format(line_id=line_id),
                params={"usage": usage, "style": style},
                headers={"apiKey": token},
            )
        except ClientError:
            return web.Response(status=502)

        if resp.status != 200:
            return web.Response(status=resp.status)

        body = await resp.read()
        content_type = resp.content_type or "image/svg+xml"
        _cache[cache_key] = (body, content_type)
        return web.Response(body=body, content_type=content_type)

    def _get_token(self) -> str | None:
        entries = self.hass.config_entries.async_entries(DOMAIN)
        return entries[0].data[CONF_TOKEN] if entries else None
