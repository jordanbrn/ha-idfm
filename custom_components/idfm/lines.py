"""Cached lookup of line display info (short name, colors) from IDFM open data.

The idfm-api package resolves line ids/names but drops the color and short-name
fields we need to render a line "picto" badge, so we fetch them separately from
the same public referentiel-des-lignes dataset.
"""
from __future__ import annotations

import asyncio
import logging

import aiohttp

from .const import LINES_DATASET_URL

_LOGGER = logging.getLogger(__name__)


class LineInfoRepository:
    """Class-level cache shared across all config entries."""

    _cache: dict[str, dict] | None = None
    _lock = asyncio.Lock()

    @classmethod
    async def get(cls, session: aiohttp.ClientSession, line_id: str) -> dict:
        if cls._cache is None:
            async with cls._lock:
                if cls._cache is None:
                    await cls._fetch(session)
        return cls._cache.get(line_id, {})

    @classmethod
    async def _fetch(cls, session: aiohttp.ClientSession) -> None:
        _LOGGER.debug("fetching IDFM lines referential")
        cache: dict[str, dict] = {}
        try:
            resp = await session.get(LINES_DATASET_URL)
            rows = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            _LOGGER.warning("failed to fetch IDFM lines referential: %s", err)
            cls._cache = {}
            return

        for row in rows:
            fields = row.get("fields", {})
            line_id = fields.get("id_line")
            if not line_id:
                continue
            color = fields.get("colourweb_hexa") or "0064B0"
            text_color = fields.get("textcolourweb_hexa") or "FFFFFF"
            cache[line_id] = {
                "short_name": fields.get("shortname_line") or fields.get("name_line"),
                "color": f"#{color}",
                "text_color": f"#{text_color}",
                "mode": fields.get("transportmode"),
                "network": fields.get("networkname"),
            }
        cls._cache = cache
