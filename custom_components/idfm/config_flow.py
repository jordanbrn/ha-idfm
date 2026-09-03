"""Config flow for the IDFM integration.

Each config entry tracks a single line (traffic status) or a single stop
(next departures) - add the integration again to track more of either.
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from aiohttp import ClientError
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from idfm_api import IDFMApi
from idfm_api.models import TransportType

from .const import (
    CONF_DESTINATION,
    CONF_DIRECTION,
    CONF_KIND,
    CONF_LINE,
    CONF_LINE_NAME,
    CONF_MODE,
    CONF_STOP,
    CONF_STOP_NAME,
    CONF_TOKEN,
    DOMAIN,
    KIND_DEPARTURES,
    KIND_TRAFFIC,
)

_LOGGER = logging.getLogger(__name__)

MODE_LABELS = {
    "metro": "Métro",
    "rail": "RER / Transilien",
    "tram": "Tramway",
    "bus": "Bus",
}

KIND_LABELS = {
    KIND_TRAFFIC: "État du trafic d'une ligne",
    KIND_DEPARTURES: "Prochains départs d'une station",
}

ANY_DIRECTION = "Toutes les directions"

# A line that is always in service, used as a lightweight ping to check the API key.
_VALIDATION_LINE_REF = "STIF:Line::C01742:"


async def _validate_token(hass, token: str) -> str | None:
    """Return an error code if the token is rejected, else None."""
    session = async_get_clientsession(hass)
    try:
        resp = await session.get(
            "https://prim.iledefrance-mobilites.fr/marketplace/general-message"
            f"?LineRef={_VALIDATION_LINE_REF}",
            headers={"apiKey": token, "Accept": "application/json"},
        )
    except ClientError:
        return "cannot_connect"

    if resp.status in (401, 403):
        return "invalid_auth"
    if resp.status != 200:
        return "cannot_connect"
    return None


class IdfmConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for IDFM."""

    VERSION = 1

    def __init__(self) -> None:
        self.data: dict[str, Any] = {}
        self._client: IDFMApi | None = None
        self._lines: list = []
        self._stops: list = []

    def _existing_token(self) -> str:
        entries = self._async_current_entries()
        return entries[0].data[CONF_TOKEN] if entries else ""

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            error = await _validate_token(self.hass, user_input[CONF_TOKEN])
            if error:
                errors["base"] = error
            else:
                self.data[CONF_TOKEN] = user_input[CONF_TOKEN]
                self._client = IDFMApi(async_get_clientsession(self.hass), self.data[CONF_TOKEN])
                return await self.async_step_kind()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_TOKEN, default=self._existing_token()): str}
            ),
            errors=errors,
        )

    async def async_step_kind(self, user_input=None):
        if user_input is not None:
            self.data[CONF_KIND] = user_input[CONF_KIND]
            return await self.async_step_mode()

        return self.async_show_form(
            step_id="kind",
            data_schema=vol.Schema({vol.Required(CONF_KIND): vol.In(KIND_LABELS)}),
        )

    async def async_step_mode(self, user_input=None):
        if user_input is not None:
            self.data[CONF_MODE] = user_input[CONF_MODE]
            return await self.async_step_line()

        return self.async_show_form(
            step_id="mode",
            data_schema=vol.Schema({vol.Required(CONF_MODE): vol.In(MODE_LABELS)}),
        )

    async def async_step_line(self, user_input=None):
        self._lines = await self._client.get_lines(TransportType(self.data[CONF_MODE]))
        names = sorted(line.name for line in self._lines)
        if not names:
            return self.async_abort(reason="no_lines")

        if user_input is not None:
            for line in self._lines:
                if line.name == user_input[CONF_LINE]:
                    self.data[CONF_LINE] = line.id
                    self.data[CONF_LINE_NAME] = line.name
                    if self.data[CONF_KIND] == KIND_TRAFFIC:
                        await self.async_set_unique_id(f"traffic_{line.id}")
                        self._abort_if_unique_id_configured()
                        return self.async_create_entry(
                            title=f"Trafic {line.name}", data=self.data
                        )
                    return await self.async_step_stop()

        return self.async_show_form(
            step_id="line",
            data_schema=vol.Schema(
                {vol.Required(CONF_LINE, default=names[0]): vol.In(names)}
            ),
        )

    async def async_step_stop(self, user_input=None):
        self._stops = await self._client.get_stops(self.data[CONF_LINE])
        labels = {f"{stop.name} - {stop.city}": stop for stop in self._stops}
        names = sorted(labels)
        if not names:
            return self.async_abort(reason="no_stops")

        if user_input is not None:
            stop = labels.get(user_input[CONF_STOP])
            if stop is not None:
                self.data[CONF_STOP] = stop.exchange_area_id or stop.stop_id
                self.data[CONF_STOP_NAME] = stop.name
                return await self.async_step_direction()

        return self.async_show_form(
            step_id="stop",
            data_schema=vol.Schema(
                {vol.Required(CONF_STOP, default=names[0]): vol.In(names)}
            ),
        )

    async def async_step_direction(self, user_input=None):
        if user_input is not None:
            self.data[CONF_DIRECTION] = None
            self.data[CONF_DESTINATION] = None
            choice = user_input[CONF_DIRECTION]
            if choice.startswith("Dir: "):
                self.data[CONF_DIRECTION] = choice[len("Dir: ") :]
            elif choice.startswith("Dest: "):
                self.data[CONF_DESTINATION] = choice[len("Dest: ") :]

            uid = (
                f"departures_{self.data[CONF_STOP]}_{self.data[CONF_LINE]}_"
                f"{self.data[CONF_DIRECTION]}_{self.data[CONF_DESTINATION]}"
            )
            await self.async_set_unique_id(uid)
            self._abort_if_unique_id_configured()

            title = f"{self.data[CONF_STOP_NAME]} ({self.data[CONF_LINE_NAME]})"
            return self.async_create_entry(title=title, data=self.data)

        directions = await self._client.get_directions(
            self.data[CONF_STOP], line_id=self.data[CONF_LINE]
        )
        destinations = await self._client.get_destinations(
            self.data[CONF_STOP], line_id=self.data[CONF_LINE]
        )
        options = (
            [ANY_DIRECTION]
            + [f"Dir: {d}" for d in directions if d]
            + [f"Dest: {d}" for d in destinations if d]
        )

        return self.async_show_form(
            step_id="direction",
            data_schema=vol.Schema(
                {vol.Required(CONF_DIRECTION, default=options[0]): vol.In(options)}
            ),
        )
