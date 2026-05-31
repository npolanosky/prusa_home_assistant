"""Prusa Connect / PrusaLink API client.

Supports two connection modes:
- Local (PrusaLink): connects directly to printer on LAN via X-Api-Key header
- Cloud (Prusa Connect): connects to connect.prusa3d.com

Authentication notes:
- PrusaLink local: X-Api-Key header (legacy API) or HTTP Digest (v1 API)
- Prusa Connect cloud: X-Api-Key header (same key works against connect.prusa3d.com
  for some endpoints), or Bearer token for OAuth2 account-level access.
  OrcaSlicer and PrusaSlicer both use X-Api-Key against connect.prusa3d.com.
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


# Auth styles we try in order during validation
AUTH_STYLES = [
    {
        "name": "X-Api-Key",
        "header_key": "X-Api-Key",
        "header_fmt": "{token}",
    },
    {
        "name": "Bearer",
        "header_key": "Authorization",
        "header_fmt": "Bearer {token}",
    },
    {
        "name": "Token",
        "header_key": "Token",
        "header_fmt": "{token}",
    },
]

# Endpoint paths we try for listing printers, in order
PRINTER_LIST_PATHS = [
    "/app/printers/",
    "/slicer/v1/printers",
    "/api/v1/printers",
]


class PrusaConnectClient:
    """Client for Prusa Connect cloud API.

    Tries multiple auth styles and endpoint paths to find the one that
    works with the user's token/key, since Prusa Connect has evolved
    its API over time and different key types work with different endpoints.
    """

    def __init__(self, token: str, session: aiohttp.ClientSession) -> None:
        self._token = token.strip()
        self._session = session
        self._base_url = PRUSA_CONNECT_CLOUD_API
        # Discovered during validate()
        self._auth_header_key: str = "X-Api-Key"
        self._auth_header_value: str = self._token
        self._printer_list_path: str = "/app/printers/"

    def _get_headers(self) -> dict[str, str]:
        return {
            self._auth_header_key: self._auth_header_value,
            "Accept": "application/json",
        }

    async def _request(
        self, method: str, path: str, label: str = "", **kwargs: Any
    ) -> tuple[int, Any]:
        """Make a request and return (status_code, parsed_body_or_None).

        Does NOT raise on HTTP errors — caller decides what to do.
        """
        url = f"{self._base_url}{path}"
        headers = self._get_headers()
        label = label or f"{method} {path}"
        _LOGGER.debug(
            "Prusa Connect request: %s %s (auth: %s)",
            method, url, self._auth_header_key,
        )
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
                        "Prusa Connect %s error body: %s",
                        label, body_text[:1000],
                    )
                data = None
                if resp.content_type and "json" in resp.content_type and body_text:
                    try:
                        import json
                        data = json.loads(body_text)
                    except Exception:
                        pass
                elif body_text.strip().startswith(("{", "[")):
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
        """Make a request using the discovered auth, raising on errors."""
        status, data = await self._request(method, path, **kwargs)
        if status in (401, 403):
            raise PrusaConnectAuthError(
                f"Auth failed (HTTP {status}) for {method} {path}"
            )
        if status >= 400:
            raise PrusaConnectError(f"HTTP {status} for {method} {path}")
        return data

    async def get_printers(self) -> list[dict[str, Any]]:
        """Get list of printers using the discovered endpoint."""
        data = await self._authed_request("GET", self._printer_list_path)
        return self._extract_printer_list(data)

    async def get_printer(self, printer_uuid: str) -> dict[str, Any]:
        """Get printer details."""
        return await self._authed_request("GET", f"/app/printers/{printer_uuid}")

    async def get_printer_status(self, printer_uuid: str) -> dict[str, Any]:
        """Get printer status - try multiple endpoint patterns."""
        for path in [
            f"/app/printers/{printer_uuid}/status",
            f"/app/printers/{printer_uuid}",
        ]:
            try:
                data = await self._authed_request("GET", path)
                if data:
                    return data
            except PrusaConnectError:
                continue
        return {}

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

    def _extract_printer_list(self, data: Any) -> list[dict[str, Any]]:
        """Extract a list of printers from various response formats."""
        if isinstance(data, list):
            _LOGGER.debug("Printers response: list with %d items", len(data))
            return data
        if isinstance(data, dict):
            for key in ("member", "printers", "data"):
                if key in data and isinstance(data[key], list):
                    items = data[key]
                    _LOGGER.debug(
                        "Printers response: dict.%s with %d items", key, len(items)
                    )
                    return items
            # Single printer object
            if any(k in data for k in ("uuid", "sn", "serial", "name")):
                _LOGGER.debug("Printers response: single printer object")
                return [data]
            _LOGGER.debug(
                "Printers response: dict with unrecognized keys: %s",
                list(data.keys())[:10],
            )
        _LOGGER.warning("Unexpected printers response type: %s", type(data))
        return []

    async def validate(self) -> tuple[bool, str]:
        """Try all auth styles × endpoint paths to find a working combination.

        Returns (success, detail_message).
        """
        attempts: list[str] = []

        for style in AUTH_STYLES:
            self._auth_header_key = style["header_key"]
            self._auth_header_value = style["header_fmt"].format(token=self._token)

            for path in PRINTER_LIST_PATHS:
                label = f'{style["name"]} → {path}'
                _LOGGER.info("Prusa Connect: trying %s", label)

                try:
                    status, data = await self._request(
                        "GET", path, label=label
                    )
                except PrusaConnectError as err:
                    msg = f"{label}: connection error ({err})"
                    _LOGGER.debug(msg)
                    attempts.append(msg)
                    continue

                if status in (401, 403):
                    msg = f"{label}: HTTP {status} (auth rejected)"
                    _LOGGER.debug(msg)
                    attempts.append(msg)
                    continue

                if status == 404:
                    msg = f"{label}: HTTP 404 (endpoint not found)"
                    _LOGGER.debug(msg)
                    attempts.append(msg)
                    continue

                if status >= 400:
                    msg = f"{label}: HTTP {status}"
                    _LOGGER.debug(msg)
                    attempts.append(msg)
                    continue

                # Success — extract printers
                printers = self._extract_printer_list(data)
                self._printer_list_path = path
                result = (
                    f'{style["name"]} auth with {path} succeeded — '
                    f"found {len(printers)} printer(s)"
                )
                _LOGGER.info("Prusa Connect: %s", result)
                return True, result

        # All failed
        summary = "All authentication attempts failed:\n" + "\n".join(
            f"  • {a}" for a in attempts
        )
        _LOGGER.warning("Prusa Connect validation failed. %s", summary)
        return False, summary


class PrusaLinkClient:
    """Client for PrusaLink local API on the printer.

    Uses the legacy X-Api-Key header for auth. The v1 API uses HTTP Digest
    but X-Api-Key works for all the endpoints we need.
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
                _LOGGER.debug("Camera snap failed: HTTP %s", resp.status)
                return None
        except aiohttp.ClientError as err:
            _LOGGER.debug("Camera snap error: %s", err)
            return None

    async def validate(self) -> tuple[bool, str]:
        """Validate the API key.

        Returns (success, detail_message).
        """
        try:
            version_data = await self.get_version()
            server = version_data.get("server", "unknown")
            text = version_data.get("text", "")
            msg = f"Connected to {text} {server} at {self._host}"
            _LOGGER.info("PrusaLink: %s", msg)
            return True, msg
        except PrusaConnectAuthError as err:
            return False, f"Authentication failed: {err}"
        except PrusaConnectError as err:
            return False, f"Connection failed: {err}"
