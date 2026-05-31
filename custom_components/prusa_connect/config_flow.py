"""Config flow for Prusa Connect integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
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
        self._printer_name: str = ""
        self._printers: list[dict[str, Any]] = []
        self._cloud_client: PrusaConnectClient | None = None
        self._last_error_detail: str = ""
        self._validation_failed: bool = False

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> PrusaConnectOptionsFlow:
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
            printer_name = user_input.get(CONF_PRINTER_NAME, "").strip()
            _LOGGER.warning("Prusa Connect: attempting PrusaLink connection to %s", host)

            session = async_get_clientsession(self.hass)
            client = PrusaLinkClient(host, api_key, session)

            validated = False
            serial = host
            detected_name = ""
            printer_type = ""

            try:
                success, detail = await client.validate()
                if success:
                    _LOGGER.warning("PrusaLink validation succeeded: %s", detail)
                    try:
                        info = await client.get_info()
                        _LOGGER.warning("PrusaLink info: %s", info)
                        serial = info.get("serial", host)
                        detected_name = info.get("name", info.get("hostname", ""))
                        printer_type = info.get("type", "")
                    except PrusaConnectError:
                        pass
                    validated = True
                    self._last_error_detail = ""
                else:
                    _LOGGER.warning("PrusaLink validation failed: %s", detail)
                    self._last_error_detail = detail
            except PrusaConnectAuthError as err:
                _LOGGER.warning("PrusaLink auth error: %s", err)
                self._last_error_detail = str(err)
            except PrusaConnectError as err:
                _LOGGER.warning("PrusaLink connection error: %s", err)
                self._last_error_detail = str(err)
            except Exception as err:
                _LOGGER.exception("Unexpected error during PrusaLink setup")
                self._last_error_detail = f"Unexpected: {err}"

            if not validated and not self._validation_failed:
                # First failure — show error and offer to try again or save anyway
                self._validation_failed = True
                self._host = host
                self._api_key = api_key
                self._printer_name = printer_name
                errors["base"] = "cannot_connect"
            else:
                # Either validated OK, or second attempt (save anyway)
                final_name = printer_name or detected_name or "Prusa Printer"

                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=final_name,
                    data={
                        CONF_CONNECTION_TYPE: CONNECTION_TYPE_LOCAL,
                        CONF_HOST: host,
                        CONF_API_KEY: api_key,
                        CONF_PRINTER_NAME: final_name,
                        CONF_PRINTER_TYPE: printer_type,
                    },
                )

        description = (
            "Connect directly to your printer on the local network.\n\n"
            "Find the API key in your printer's web interface at "
            "**http://your-printer-ip** → Settings → API Key."
        )
        if self._last_error_detail:
            description += (
                f"\n\n**Last error:** {self._last_error_detail}"
                "\n\n**Submit again with the same or updated values to save anyway** "
                "— you can fix the connection later in the integration options."
            )

        return self.async_show_form(
            step_id="local",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=self._host): str,
                    vol.Required(CONF_API_KEY, default=self._api_key): str,
                    vol.Optional(CONF_PRINTER_NAME, default=self._printer_name or vol.UNDEFINED): str,
                }
            ),
            errors=errors,
        )

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle cloud Prusa Connect setup."""
        errors: dict[str, str] = {}

        if user_input is not None:
            token = user_input[CONF_API_KEY].strip()
            printer_name = user_input.get(CONF_PRINTER_NAME, "").strip()
            _LOGGER.warning(
                "Prusa Connect: attempting cloud auth (key length: %d, starts: %s...)",
                len(token),
                token[:4] if len(token) > 4 else "***",
            )

            session = async_get_clientsession(self.hass)
            client = PrusaConnectClient(token, session)

            validated = False
            try:
                success, detail = await client.validate()
                if success:
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
                    if printers:
                        self._api_key = token
                        self._printers = printers
                        self._cloud_client = client
                        self._last_error_detail = ""
                        return await self.async_step_select_printer()
                    else:
                        self._last_error_detail = (
                            "API connected successfully but no printers were returned. "
                            "Make sure your printer is registered in Prusa Connect."
                        )
                else:
                    _LOGGER.warning("Prusa Connect cloud validation failed:\n%s", detail)
                    self._last_error_detail = detail
            except PrusaConnectAuthError as err:
                _LOGGER.warning("Prusa Connect cloud auth error: %s", err)
                self._last_error_detail = str(err)
            except PrusaConnectError as err:
                _LOGGER.warning("Prusa Connect cloud connection error: %s", err)
                self._last_error_detail = str(err)
            except Exception as err:
                _LOGGER.exception("Unexpected error during Prusa Connect cloud setup")
                self._last_error_detail = f"Unexpected: {err}"

            if not self._validation_failed:
                # First failure — show error, let them retry or save
                self._validation_failed = True
                self._api_key = token
                self._printer_name = printer_name
                errors["base"] = "invalid_auth"
            else:
                # Second attempt — save anyway without validation
                final_name = printer_name or "Prusa Printer (Cloud)"

                return self.async_create_entry(
                    title=final_name,
                    data={
                        CONF_CONNECTION_TYPE: CONNECTION_TYPE_CLOUD,
                        CONF_API_KEY: token,
                        CONF_PRINTER_UUID: "",
                        CONF_PRINTER_NAME: final_name,
                        CONF_PRINTER_TYPE: "",
                    },
                )

        description = (
            "Connect via the Prusa Connect cloud at "
            "[https://connect.prusa3d.com](https://connect.prusa3d.com).\n\n"
            "Find your API key at **connect.prusa3d.com** → select your printer → "
            "**Settings** tab → scroll to **API keys**. "
            "This is the same key used in PrusaSlicer and OrcaSlicer."
        )
        if self._last_error_detail:
            description += (
                f"\n\n**Last error:**\n{self._last_error_detail}"
                "\n\n**Submit again to save anyway** — you can fix the connection "
                "later in the integration options. Add a printer name below if saving without connection."
            )

        schema_fields: dict = {
            vol.Required(CONF_API_KEY, default=self._api_key): str,
        }
        if self._validation_failed:
            schema_fields[vol.Optional(CONF_PRINTER_NAME, default=self._printer_name or vol.UNDEFINED)] = str

        return self.async_show_form(
            step_id="cloud",
            data_schema=vol.Schema(schema_fields),
            errors=errors,
            description_placeholders={
                "prusa_connect_url": "https://connect.prusa3d.com",
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
    """Handle options flow for Prusa Connect.

    Allows editing API key, host, printer name, and scan interval
    after initial setup — even if the initial connection failed.
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show the options form with all editable fields."""
        errors: dict[str, str] = {}
        description = "Update your Prusa Connect configuration."

        if user_input is not None:
            _LOGGER.warning("Prusa Connect options: user submitted: %s",
                {k: v for k, v in user_input.items() if k != CONF_API_KEY})

            # Test the new connection settings if key or host changed
            new_api_key = user_input.get(CONF_API_KEY, "").strip()
            new_host = user_input.get(CONF_HOST, "").strip()
            connection_type = self._config_entry.data.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_LOCAL)
            test_detail = ""

            if new_api_key:
                session = async_get_clientsession(self.hass)
                if connection_type == CONNECTION_TYPE_LOCAL and new_host:
                    client = PrusaLinkClient(new_host, new_api_key, session)
                    success, test_detail = await client.validate()
                    if success:
                        _LOGGER.warning("Options: PrusaLink test succeeded: %s", test_detail)
                    else:
                        _LOGGER.warning("Options: PrusaLink test failed: %s", test_detail)
                elif connection_type == CONNECTION_TYPE_CLOUD:
                    client = PrusaConnectClient(new_api_key, session)
                    success, test_detail = await client.validate()
                    if success:
                        _LOGGER.warning("Options: Cloud test succeeded: %s", test_detail)
                    else:
                        _LOGGER.warning("Options: Cloud test failed: %s", test_detail)

            # Build updated data — merge with existing
            new_data = dict(self._config_entry.data)
            if new_api_key:
                new_data[CONF_API_KEY] = new_api_key
            if new_host:
                new_data[CONF_HOST] = new_host
            new_printer_name = user_input.get(CONF_PRINTER_NAME, "").strip()
            if new_printer_name:
                new_data[CONF_PRINTER_NAME] = new_printer_name
            new_uuid = user_input.get(CONF_PRINTER_UUID, "").strip()
            if new_uuid:
                new_data[CONF_PRINTER_UUID] = new_uuid

            # Update the config entry data
            self.hass.config_entries.async_update_entry(
                self._config_entry,
                data=new_data,
                title=new_data.get(CONF_PRINTER_NAME, self._config_entry.title),
            )

            # Save options (scan interval)
            new_options = dict(self._config_entry.options)
            scan_interval = user_input.get("scan_interval")
            if scan_interval is not None:
                new_options["scan_interval"] = scan_interval

            # Reload the integration to pick up changes
            await self.hass.config_entries.async_reload(self._config_entry.entry_id)

            return self.async_create_entry(title="", data=new_options)

        # Build the schema based on connection type
        connection_type = self._config_entry.data.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_LOCAL)
        current_data = self._config_entry.data

        schema_fields: dict[vol.Marker, type] = {}

        if connection_type == CONNECTION_TYPE_LOCAL:
            schema_fields[vol.Optional(
                CONF_HOST,
                description={"suggested_value": current_data.get(CONF_HOST, "")},
            )] = str

        schema_fields[vol.Optional(
            CONF_API_KEY,
            description={"suggested_value": current_data.get(CONF_API_KEY, "")},
        )] = str

        schema_fields[vol.Optional(
            CONF_PRINTER_NAME,
            description={"suggested_value": current_data.get(CONF_PRINTER_NAME, "")},
        )] = str

        if connection_type == CONNECTION_TYPE_CLOUD:
            schema_fields[vol.Optional(
                CONF_PRINTER_UUID,
                description={"suggested_value": current_data.get(CONF_PRINTER_UUID, "")},
            )] = str

        schema_fields[vol.Optional(
            "scan_interval",
            default=self._config_entry.options.get("scan_interval", 30),
        )] = vol.All(vol.Coerce(int), vol.Range(min=10, max=300))

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_fields),
            errors=errors,
        )
