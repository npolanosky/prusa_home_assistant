"""Config flow for Prusa Connect integration.

Two connection modes:
  - Local (PrusaLink): host + API key, validated against the printer's LAN IP.
  - Cloud (Prusa Connect): Prusa *account* OAuth2 (Authorization-Code + PKCE),
    mirroring PrusaSlicer. The user logs in via a browser, copies the resulting
    authorization code, and we exchange it for tokens.
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    PrusaConnectClient,
    PrusaConnectError,
    PrusaLinkClient,
    build_authorize_url,
    extract_code,
    generate_pkce_pair,
)
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_API_KEY,
    CONF_AUTH_CODE,
    CONF_CONNECTION_TYPE,
    CONF_HOST,
    CONF_PRINTER_NAME,
    CONF_PRINTER_TYPE,
    CONF_PRINTER_UUID,
    CONF_REFRESH_TOKEN,
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
        self._last_error_detail: str = ""
        self._validation_failed: bool = False
        # Cloud / OAuth state
        self._code_verifier: str = ""
        self._code_challenge: str = ""
        self._access_token: str = ""
        self._refresh_token: str = ""
        self._printers: list[dict[str, Any]] = []

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> PrusaConnectOptionsFlow:
        return PrusaConnectOptionsFlow(config_entry)

    # -- Step 1: choose connection type -------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self._connection_type = user_input[CONF_CONNECTION_TYPE]
            _LOGGER.warning("Prusa Connect: connection type: %s", self._connection_type)
            if self._connection_type == CONNECTION_TYPE_LOCAL:
                return await self.async_step_local()
            return await self.async_step_cloud()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CONNECTION_TYPE, default=CONNECTION_TYPE_LOCAL): vol.In(
                        {
                            CONNECTION_TYPE_LOCAL: "Local (PrusaLink — printer IP + API key)",
                            CONNECTION_TYPE_CLOUD: "Cloud (Prusa Connect — log in with Prusa account)",
                        }
                    ),
                }
            ),
        )

    # -- Local (PrusaLink) ---------------------------------------------------

    async def async_step_local(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            api_key = user_input[CONF_API_KEY]
            printer_name = user_input.get(CONF_PRINTER_NAME, "").strip()
            _LOGGER.warning("Prusa Connect: PrusaLink connection to %s", host)

            session = async_get_clientsession(self.hass)
            client = PrusaLinkClient(host, api_key, session)

            validated = False
            serial = host
            detected_name = ""
            printer_type = ""

            try:
                success, detail = await client.validate()
                if success:
                    try:
                        info = await client.get_info()
                        serial = info.get("serial", host)
                        detected_name = info.get("name", info.get("hostname", ""))
                        printer_type = info.get("type", "")
                    except PrusaConnectError:
                        pass
                    validated = True
                    self._last_error_detail = ""
                else:
                    self._last_error_detail = detail
            except PrusaConnectError as err:
                self._last_error_detail = str(err)
            except Exception as err:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during PrusaLink setup")
                self._last_error_detail = f"Unexpected: {err}"

            if not validated and not self._validation_failed:
                self._validation_failed = True
                self._host = host
                self._api_key = api_key
                self._printer_name = printer_name
                errors["base"] = "cannot_connect"
            else:
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
                "\n\n**Submit again to save anyway** — you can fix the "
                "connection later in the integration options."
            )

        return self.async_show_form(
            step_id="local",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=self._host): str,
                    vol.Required(CONF_API_KEY, default=self._api_key): str,
                    vol.Optional(
                        CONF_PRINTER_NAME,
                        default=self._printer_name or vol.UNDEFINED,
                    ): str,
                }
            ),
            errors=errors,
            description_placeholders={"error_detail": self._last_error_detail},
        )

    # -- Cloud (Prusa Connect OAuth2) ---------------------------------------

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show the login link and accept the pasted authorization code."""
        errors: dict[str, str] = {}

        # Generate a PKCE pair the first time we show this step.
        if not self._code_verifier:
            self._code_verifier, self._code_challenge = generate_pkce_pair()

        authorize_url = build_authorize_url(self._code_challenge)

        if user_input is not None:
            raw = user_input.get(CONF_AUTH_CODE, "").strip()
            code = extract_code(raw)
            if not code:
                errors["base"] = "invalid_code"
                self._last_error_detail = "No authorization code was provided."
            else:
                session = async_get_clientsession(self.hass)
                client = PrusaConnectClient(session)
                ok, detail = await client.async_exchange_code(code, self._code_verifier)
                if not ok:
                    errors["base"] = "invalid_auth"
                    self._last_error_detail = detail
                    # Regenerate PKCE so the next attempt uses a fresh challenge.
                    self._code_verifier, self._code_challenge = generate_pkce_pair()
                else:
                    self._access_token = client.access_token or ""
                    self._refresh_token = client.refresh_token or ""
                    # Fetch the printer list for selection.
                    try:
                        self._printers = await client.get_printers()
                    except PrusaConnectError as err:
                        _LOGGER.warning("Prusa Connect: get_printers failed: %s", err)
                        self._printers = []
                    return await self.async_step_select_printer()

        description = (
            "**Step 1.** Open this link and log in with your Prusa account, then "
            "approve access:\n\n"
            f"[Log in to Prusa Connect]({authorize_url})\n\n"
            "**Step 2.** Your browser will try to open a `prusaslicer://login…` "
            "link and show an error — that's expected. Copy the **entire URL** "
            "from the address bar (it contains `?code=…`) and paste it below. "
            "You can also paste just the code value."
        )
        if self._last_error_detail:
            description += f"\n\n**Last error:** {self._last_error_detail}"

        return self.async_show_form(
            step_id="cloud",
            data_schema=vol.Schema({vol.Required(CONF_AUTH_CODE): str}),
            errors=errors,
            description_placeholders={"authorize_url": authorize_url},
        )

    async def async_step_select_printer(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Pick which printer to add (or enter a UUID manually)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            uuid = user_input.get(CONF_PRINTER_UUID, "").strip()
            name = user_input.get(CONF_PRINTER_NAME, "").strip()
            if not uuid:
                errors["base"] = "no_printer_selected"
            else:
                detected = next(
                    (p for p in self._printers if self._printer_id(p) == uuid), {}
                )
                final_name = (
                    name
                    or detected.get("name")
                    or detected.get("printer_name")
                    or "Prusa Printer (Cloud)"
                )
                ptype = detected.get("printer_type", detected.get("type", ""))
                await self.async_set_unique_id(uuid)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=final_name,
                    data={
                        CONF_CONNECTION_TYPE: CONNECTION_TYPE_CLOUD,
                        CONF_ACCESS_TOKEN: self._access_token,
                        CONF_REFRESH_TOKEN: self._refresh_token,
                        CONF_PRINTER_UUID: uuid,
                        CONF_PRINTER_NAME: final_name,
                        CONF_PRINTER_TYPE: ptype,
                    },
                )

        # Build the schema: a dropdown if we discovered printers, else free text.
        if self._printers:
            choices = {
                self._printer_id(p): self._printer_label(p) for p in self._printers
            }
            schema = vol.Schema(
                {
                    vol.Required(CONF_PRINTER_UUID): vol.In(choices),
                    vol.Optional(CONF_PRINTER_NAME): str,
                }
            )
            description = "Select the printer you want to add to Home Assistant."
        else:
            schema = vol.Schema(
                {
                    vol.Required(CONF_PRINTER_UUID): str,
                    vol.Optional(CONF_PRINTER_NAME): str,
                }
            )
            description = (
                "Authenticated successfully, but no printers were returned "
                "automatically. Enter your Printer UUID manually — find it in the "
                "connect.prusa3d.com URL when viewing your printer."
            )

        return self.async_show_form(
            step_id="select_printer",
            data_schema=schema,
            errors=errors,
            description_placeholders={"description": description},
        )

    @staticmethod
    def _printer_id(printer: dict[str, Any]) -> str:
        return str(printer.get("uuid") or printer.get("printer_uuid") or "")

    @staticmethod
    def _printer_label(printer: dict[str, Any]) -> str:
        name = printer.get("name") or printer.get("printer_name") or "Printer"
        ptype = printer.get("printer_type") or printer.get("type") or ""
        uuid = PrusaConnectConfigFlow._printer_id(printer)
        label = name
        if ptype:
            label += f" ({ptype})"
        if uuid:
            label += f" — {uuid[:8]}…"
        return label


class PrusaConnectOptionsFlow(OptionsFlow):
    """Options flow — edit settings and re-authenticate after setup."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry
        self._code_verifier: str = ""
        self._code_challenge: str = ""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        connection_type = self._config_entry.data.get(
            CONF_CONNECTION_TYPE, CONNECTION_TYPE_LOCAL
        )

        if user_input is not None:
            # A request to re-run the cloud login.
            if connection_type == CONNECTION_TYPE_CLOUD and user_input.get("reauth"):
                return await self.async_step_reauth()

            new_data = dict(self._config_entry.data)
            new_host = user_input.get(CONF_HOST, "").strip()
            new_api_key = user_input.get(CONF_API_KEY, "").strip()
            new_name = user_input.get(CONF_PRINTER_NAME, "").strip()
            new_uuid = user_input.get(CONF_PRINTER_UUID, "").strip()
            if new_host:
                new_data[CONF_HOST] = new_host
            if new_api_key:
                new_data[CONF_API_KEY] = new_api_key
            if new_name:
                new_data[CONF_PRINTER_NAME] = new_name
            if new_uuid:
                new_data[CONF_PRINTER_UUID] = new_uuid

            self.hass.config_entries.async_update_entry(
                self._config_entry,
                data=new_data,
                title=new_data.get(CONF_PRINTER_NAME, self._config_entry.title),
            )

            new_options = dict(self._config_entry.options)
            scan_interval = user_input.get("scan_interval")
            if scan_interval is not None:
                new_options["scan_interval"] = scan_interval

            await self.hass.config_entries.async_reload(self._config_entry.entry_id)
            return self.async_create_entry(title="", data=new_options)

        current = self._config_entry.data
        fields: dict[vol.Marker, Any] = {}

        if connection_type == CONNECTION_TYPE_LOCAL:
            fields[vol.Optional(
                CONF_HOST,
                description={"suggested_value": current.get(CONF_HOST, "")},
            )] = str
            fields[vol.Optional(
                CONF_API_KEY,
                description={"suggested_value": current.get(CONF_API_KEY, "")},
            )] = str

        fields[vol.Optional(
            CONF_PRINTER_NAME,
            description={"suggested_value": current.get(CONF_PRINTER_NAME, "")},
        )] = str

        if connection_type == CONNECTION_TYPE_CLOUD:
            fields[vol.Optional(
                CONF_PRINTER_UUID,
                description={"suggested_value": current.get(CONF_PRINTER_UUID, "")},
            )] = str
            fields[vol.Optional("reauth", default=False)] = bool

        fields[vol.Optional(
            "scan_interval",
            default=self._config_entry.options.get("scan_interval", 30),
        )] = vol.All(vol.Coerce(int), vol.Range(min=10, max=300))

        return self.async_show_form(step_id="init", data_schema=vol.Schema(fields))

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Re-run the Prusa account OAuth login from the options menu."""
        errors: dict[str, str] = {}

        if not self._code_verifier:
            self._code_verifier, self._code_challenge = generate_pkce_pair()
        authorize_url = build_authorize_url(self._code_challenge)

        if user_input is not None:
            code = extract_code(user_input.get(CONF_AUTH_CODE, ""))
            session = async_get_clientsession(self.hass)
            client = PrusaConnectClient(session)
            ok, detail = await client.async_exchange_code(code, self._code_verifier)
            if not ok:
                errors["base"] = "invalid_auth"
                self._code_verifier, self._code_challenge = generate_pkce_pair()
            else:
                new_data = dict(self._config_entry.data)
                new_data[CONF_ACCESS_TOKEN] = client.access_token
                new_data[CONF_REFRESH_TOKEN] = client.refresh_token
                self.hass.config_entries.async_update_entry(
                    self._config_entry, data=new_data
                )
                await self.hass.config_entries.async_reload(
                    self._config_entry.entry_id
                )
                return self.async_create_entry(title="", data=dict(
                    self._config_entry.options
                ))

        return self.async_show_form(
            step_id="reauth",
            data_schema=vol.Schema({vol.Required(CONF_AUTH_CODE): str}),
            errors=errors,
            description_placeholders={"authorize_url": authorize_url},
        )
