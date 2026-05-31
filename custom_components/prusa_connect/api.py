"""Prusa Connect / PrusaLink API client.

Supports two connection modes:
- Local (PrusaLink): connects directly to printer on LAN via X-Api-Key header
- Cloud (Prusa Connect): connects to connect.prusa3d.com via per-printer API key

The Prusa Connect API key is per-printer (not per-account). It authenticates
via X-Api-Key header against connect.prusa3d.com/api/... endpoints.
The printer UUID is required for most endpoints.
"""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import PRUSA_CONNECT_CLOUD_API

_LOGGER = logging.getLogger(__name__)


class PrusaConnectError(Exception):
    """Base exception for Prusa Connect API errors."""


class PrusaConnectAuthError(PrusaConnectError):
    """Authentication error."""


class PrusaConnectClient:
    """Client for Prusa Connect cloud API.

    Uses a per-printer API key with X-Api-Key header against
    connect.prusa3d.com. The API key is scoped to a single printer
    and must be paired with that printer's UUID.
    """

    def __init__(self, api_key: str, session: aiohttp.ClientSession) -> None:
        self._api_key = api_key.strip()
        self._session = session
        self._base_url = PRUSA_CONNECT_CLOUD_API

    def _get_headers(self) -> dict[str, str]:
        return {
            "X-Api-Key": self._api_key,
            "Accept": "application/json",
        }

    async def _request(
        self, method: str, path: str, label: str = "", **kwargs: Any
    ) -> tuple[int, Any]:
        """Make a request and return (status_code, parsed_body_or_None)."""
        url = f"{self._base_url}{path}"
        headers = self._get_headers()
        label = label or f"{method} {path}"
        _LOGGER.debug("Prusa Connect request: %s %s", method, url)
        try:
            async with self._session.request(
                method, url, headers=headers, allow_redirects=True, **kwargs
            ) as resp:
                body_text = await resp.text()
                _LOGGER.debug(
                    "Prusa Connect response: %s -> HTTP %s (%d bytes, content-type: %s)",
                    label, resp.status, len(body_text), resp.content_type,
                )
                if resp.status >= 400:
                    _LOGGER.debug(
                        "Prusa Connect %s error body: %s", label, body_text[:1000],
                    )
                data = None
                if body_text.strip().startswith(("{", "[")):
                    try:
                        import json
                        data = json.loads(body_text)
                    except Exception:
                        pass
                return resp.status, data
        except aiohttp.ClientError as err:
            _LOGGER.error("Prusa Connect connection error for %s: %s", label, err)
            raise PrusaConnectError(f"Connection error: {err}") from err

    async def _authed_request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Make a request, raising on auth/HTTP errors."""
        status, data = await self._request(method, path, **kwargs)
        if status in (401, 403):
            raise PrusaConnectAuthError(f"Auth failed (HTTP {status}) for {method} {path}")
        if status >= 400:
            raise PrusaConnectError(f"HTTP {status} for {method} {path}")
        return data

    async def validate_key(self) -> tuple[bool, str]:
        """Validate the API key works against connect.prusa3d.com."""
        _LOGGER.warning("Prusa Connect: validating API key against /api/version")
        try:
            status, data = await self._request("GET", "/api/version", label="validate")
            if status == 200 and data:
                server = data.get("server", "unknown")
                text = data.get("text", "PrusaConnect")
                msg = f"API key valid — connected to {text} {server}"
                _LOGGER.warning("Prusa Connect: %s", msg)
                return True, msg
            elif status in (401, 403):
                msg = f"API key rejected (HTTP {status})"
                _LOGGER.warning("Prusa Connect: %s", msg)
                return False, msg
            else:
                msg = f"Unexpected response: HTTP {status}"
                _LOGGER.warning("Prusa Connect: %s", msg)
                return False, msg
        except PrusaConnectError as err:
            return False, f"Connection failed: {err}"

    async def validate_printer(self, printer_uuid: str) -> tuple[bool, str]:
        """Validate the API key works for a specific printer UUID."""
        _LOGGER.warning(
            "Prusa Connect: validating printer UUID %s", printer_uuid
        )
        try:
            status, data = await self._request(
                "GET", f"/app/printers/{printer_uuid}",
                label=f"validate printer {printer_uuid}",
            )
            if status == 200 and data:
                name = data.get("name", data.get("hostname", ""))
                ptype = data.get("printer_type", data.get("type", ""))
                state = data.get("state", "")
                msg = f"Printer found: {name} ({ptype}) [{state}]"
                _LOGGER.warning("Prusa Connect: %s", msg)
                return True, msg
            elif status in (401, 403):
                return False, f"API key not authorized for printer {printer_uuid} (HTTP {status})"
            elif status == 404:
                return False, f"Printer UUID {printer_uuid} not found (HTTP 404)"
            else:
                body_msg = ""
                if data and isinstance(data, dict):
                    body_msg = data.get("message", "")
                return False, f"HTTP {status}: {body_msg}"
        except PrusaConnectError as err:
            return False, f"Connection error: {err}"

    async def get_printer(self, printer_uuid: str) -> dict[str, Any]:
        """Get printer details."""
        return await self._authed_request("GET", f"/app/printers/{printer_uuid}")

    async def get_printer_status(self, printer_uuid: str) -> dict[str, Any]:
        """Get printer status."""
        try:
            return await self._authed_request("GET", f"/app/printers/{printer_uuid}/status")
        except PrusaConnectError:
            # Fall back to main printer endpoint
            return await self._authed_request("GET", f"/app/printers/{printer_uuid}")

    async def get_jobs(self, printer_uuid: str) -> list[dict[str, Any]]:
        """Get current jobs for a printer."""
        for path in [
            f"/app/printers/{printer_uuid}/job",
            f"/app/printers/{printer_uuid}/jobs",
        ]:
            try:
                data = await self._authed_request("GET", path)
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    if "id" in data or "state" in data:
                        return [data]
                    for key in ("member", "jobs", "data"):
                        if key in data:
                            return data[key]
                return []
            except PrusaConnectError:
                continue
        return []


class PrusaLinkClient:
    """Client for PrusaLink local API on the printer.

    Uses X-Api-Key header for authentication against the printer's
    local web interface.
    """

    def __init__(self, host: str, api_key: str, session: aiohttp.ClientSession) -> None:
        self._host = host.rstrip("/")
        self._api_key = api_key
        self._session = session
        if not self._host.startswith("http"):
            self._host = f"http://{self._host}"

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "X-Api-Key": self._api_key,
            "Accept": "application/json",
        }

    async def _request(self, path: str) -> Any:
        url = f"{self._host}{path}"
        _LOGGER.debug("PrusaLink request: GET %s", url)
        try:
            async with self._session.get(
                url, headers=self._headers, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                _LOGGER.debug(
                    "PrusaLink response: GET %s -> HTTP %s (content-type: %s)",
                    url, resp.status, resp.content_type,
                )
                if resp.status in (401, 403):
                    body = await resp.text()
                    _LOGGER.warning(
                        "PrusaLink auth failed: HTTP %s for %s — body: %s",
                        resp.status, url, body[:500],
                    )
                    raise PrusaConnectAuthError(f"Invalid API key (HTTP {resp.status})")
                if resp.status == 204:
                    return None
                if resp.status >= 400:
                    body = await resp.text()
                    _LOGGER.error(
                        "PrusaLink error: HTTP %s for %s — body: %s",
                        resp.status, url, body[:500],
                    )
                resp.raise_for_status()
                data = await resp.json()
                _LOGGER.debug(
                    "PrusaLink response data keys: %s",
                    list(data.keys()) if isinstance(data, dict) else type(data).__name__,
                )
                return data
        except aiohttp.ClientError as err:
            _LOGGER.error("PrusaLink connection error for %s: %s", url, err)
            raise PrusaConnectError(f"Connection error: {err}") from err

    async def get_version(self) -> dict[str, Any]:
        return await self._request("/api/version")

    async def get_info(self) -> dict[str, Any]:
        return await self._request("/api/v1/info")

    async def get_status(self) -> dict[str, Any]:
        return await self._request("/api/v1/status")

    async def get_job(self) -> dict[str, Any] | None:
        return await self._request("/api/v1/job")

    async def get_camera_snap(self) -> bytes | None:
        url = f"{self._host}/api/v1/cameras/snap"
        try:
            async with self._session.get(
                url, headers=self._headers, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                if resp.status == 200:
                    return await resp.read()
                return None
        except aiohttp.ClientError:
            return None

    async def validate(self) -> tuple[bool, str]:
        """Validate the API key."""
        try:
            version_data = await self.get_version()
            server = version_data.get("server", "unknown")
            text = version_data.get("text", "")
            msg = f"Connected to {text} {server} at {self._host}"
            _LOGGER.warning("PrusaLink: %s", msg)
            return True, msg
        except PrusaConnectAuthError as err:
            return False, f"Authentication failed: {err}"
        except PrusaConnectError as err:
            return False, f"Connection failed: {err}"
