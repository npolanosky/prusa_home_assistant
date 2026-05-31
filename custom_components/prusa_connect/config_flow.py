"""Config flow for Prusa Connect integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import PrusaConnectClient, PrusaLinkClient, PrusaConnectAuthError, PrusaConnectError
from .const import (
    CONF_API_KEY,
    CONF_CONNECTION_TYPE,
    CONF_HOST,
    CONF_PRINTER_NAME,
    CONF_PRINTER_TYPE,
    CONF_PRINTER_UUID,
    CONNECTION_TYPE_CLOUD,
    CONNECTION_TYPE_LOCAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_VERSION = 1


class PrusaConnectConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Prusa Connect."""

    VERSION = CONFIG_VERSION

    def __init__(self) -> None:
        self._connection_type: str = ""
        self._api_key: str = ""
        self._host: str = ""
        self._printers: list[dict[str, Any]] = []
        self._cloud_client: PrusaConnectClient | None = None
        self._last_error_detail: str = ""

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return PrusaConnectOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the first step — choose connection type."""
        if user_input is not None:
            self._connection_type = user_input[CONF_CONNECTION_TYPE]
            _LOGGER.warning("Prusa Connect: user selected connection type: %s", self._connection_type)
            if self._connection_type == CONNECTION_TYPE_LOCAL:
                return await self.async_step_local()
            return await self.async_step_cloud()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CONNECTION_TYPE, default=CONNECTION_TYPE_LOCAL): vol.In(
                        {
                            CONNECTION_TYPE_LOCAL: "Local (PrusaLink — connect via printer IP)",
                            CONNECTION_TYPE_CLOUD: "Cloud (Prusa Connect — via API key from connect.prusa3d.com)",
                        }
                    ),
                }
            ),
        )

    async def async_step_local(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle local PrusaLink connection setup."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            api_key = user_input[CONF_API_KEY]
            _LOGGER.warning("Prusa Connect: attempting PrusaLink connection to %s", host)

            session = async_get_clientsession(self.hass)
            client = PrusaLinkClient(host, api_key, session)

            try:
                success, detail = await client.validate()
                if not success:
                    _LOGGER.warning("PrusaLink validation failed: %s", detail)
                    errors["base"] = "cannot_connect"
                    self._last_error_detail = detail
                else:
                    _LOGGER.warning("PrusaLink validation succeeded: %s", detail)
                    info = await client.get_info()
                    _LOGGER.warning("PrusaLink info: %s", info)

                    printer_name = user_input.get(
                        CONF_PRINTER_NAME,
                        info.get("name", info.get("hostname", "Prusa Printer")),
                    )
                    serial = info.get("serial", host)

                    await self.async_set_unique_id(serial)
                    self._abort_if_unique_id_configured()

                    return self.async_create_entry(
                        title=printer_name,
                        data={
                            CONF_CONNECTION_TYPE: CONNECTION_TYPE_LOCAL,
                            CONF_HOST: host,
                            CONF_API_KEY: api_key,
                            CONF_PRINTER_NAME: printer_name,
                            CONF_PRINTER_TYPE: info.get("type", ""),
                        },
                    )
            except PrusaConnectAuthError as err:
                _LOGGER.warning("PrusaLink auth error: %s", err)
                errors["base"] = "invalid_auth"
                self._last_error_detail = str(err)
            except PrusaConnectError as err:
                _LOGGER.warning("PrusaLink connection error: %s", err)
                errors["base"] = "cannot_connect"
                self._last_error_detail = str(err)
            except Exception as err:
                _LOGGER.exception("Unexpected error during PrusaLink setup")
                errors["base"] = "cannot_connect"
                self._last_error_detail = f"Unexpected: {err}"

        description = (
            "Connect directly to your printer on the local network.\n\n"
            "Find the API key in your printer's web interface at "
            "**http://your-printer-ip** → Settings → API Key."
        )
        if self._last_error_detail:
            description += f"\n\n**Last error:** {self._last_error_detail}"

        return self.async_show_form(
            step_id="local",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Required(CONF_API_KEY): str,
                    vol.Optional(CONF_PRINTER_NAME): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "error_detail": self._last_error_detail,
            },
        )

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle cloud Prusa Connect setup."""
        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input[CONF_API_KEY].strip()
            _LOGGER.warning(
                "Prusa Connect: attempting cloud auth (key length: %d, starts: %s...)",
                len(token),
                token[:4] if len(token) > 4 else "***",
            )

            session = async_get_clientsession(self.hass)
            client = PrusaConnectClient(token, session)

            try:
                success, detail = await client.validate()
                if not success:
                    _LOGGER.warning("Prusa Connect cloud validation failed:\n%s", detail)
                    errors["base"] = "invalid_auth"
                    self._last_error_detail = detail
                else:
                    _LOGGER.warning("Prusa Connect cloud validation succeeded: %s", detail)
                    printers = await client.get_printers()
                    _LOGGER.warning(
                        "Prusa Connect returned %d printer(s): %s",
                        len(printers),
                        [
                            {k: p.get(k) for k in ("uuid", "name", "state", "printerType", "sn") if k in p}
                            for p in printers
                        ],
                    )
                    if not printers:
                        errors["base"] = "no_printers"
                        self._last_error_detail = (
                            "API connected successfully but no printers were returned. "
                            "Make sure your printer is registered in Prusa Connect."
                        )
                    else:
                        self._api_key = token
                        self._printers = printers
                        self._cloud_client = client
                        return await self.async_step_select_printer()
            except PrusaConnectAuthError as err:
                _LOGGER.warning("Prusa Connect cloud auth error: %s", err)
                errors["base"] = "invalid_auth"
                self._last_error_detail = str(err)
            except PrusaConnectError as err:
                _LOGGER.warning("Prusa Connect cloud connection error: %s", err)
                errors["base"] = "cannot_connect"
                self._last_error_detail = str(err)
            except Exception as err:
                _LOGGER.exception("Unexpected error during Prusa Connect cloud setup")
                errors["base"] = "cannot_connect"
                self._last_error_detail = f"Unexpected: {err}"

        description = (
            "Connect via the Prusa Connect cloud at "
            "[https://connect.prusa3d.com](https://connect.prusa3d.com).\n\n"
            "Find your API key at **connect.prusa3d.com** → select your printer → "
            "**Settings** tab → scroll to **API keys**. "
            "This is the same key used in PrusaSlicer and OrcaSlicer."
        )
        if self._last_error_detail:
            description += f"\n\n**Last error:**\n{self._last_error_detail}"

        return self.async_show_form(
            step_id="cloud",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "prusa_connect_url": "https://connect.prusa3d.com",
                "error_detail": self._last_error_detail,
            },
        )

    async def async_step_select_printer(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle printer selection step for cloud connection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            printer_uuid = user_input[CONF_PRINTER_UUID]
            _LOGGER.warning("Prusa Connect: user selected printer UUID: %s", printer_uuid)
            printer = next(
                (p for p in self._printers if self._get_uuid(p) == printer_uuid),
                None,
            )

            if printer is None:
                _LOGGER.error(
                    "Selected UUID %s not found in printer list: %s",
                    printer_uuid,
                    [self._get_uuid(p) for p in self._printers],
                )
                errors["base"] = "printer_not_found"
            else:
                await self.async_set_unique_id(printer_uuid)
                self._abort_if_unique_id_configured()

                printer_name = printer.get("name", "Prusa Printer")
                printer_type = printer.get("printerType", printer.get("printer_type", ""))
                _LOGGER.warning(
                    "Prusa Connect: creating entry for printer: name=%s type=%s uuid=%s",
                    printer_name, printer_type, printer_uuid,
                )

                return self.async_create_entry(
                    title=printer_name,
                    data={
                        CONF_CONNECTION_TYPE: CONNECTION_TYPE_CLOUD,
                        CONF_API_KEY: self._api_key,
                        CONF_PRINTER_UUID: printer_uuid,
                        CONF_PRINTER_NAME: printer_name,
                        CONF_PRINTER_TYPE: printer_type,
                    },
                )

        printer_options = {
            self._get_uuid(p): self._get_printer_label(p)
            for p in self._printers
        }

        return self.async_show_form(
            step_id="select_printer",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PRINTER_UUID): vol.In(printer_options),
                }
            ),
            errors=errors,
        )

    @staticmethod
    def _get_uuid(printer: dict) -> str:
        return printer.get("uuid", printer.get("id", printer.get("sn", "")))

    @staticmethod
    def _get_printer_label(printer: dict) -> str:
        name = printer.get("name", "Unknown")
        ptype = printer.get("printerType", printer.get("printer_type", ""))
        state = printer.get("state", "")
        parts = [name]
        if ptype:
            parts.append(f"({ptype})")
        if state:
            parts.append(f"[{state}]")
        return " ".join(parts)


class PrusaConnectOptionsFlow(OptionsFlow):
    """Handle options flow for Prusa Connect."""

    def __init__(self, config_entry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "scan_interval",
                        default=self._config_entry.options.get("scan_interval", 30),
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
                }
            ),
        )
