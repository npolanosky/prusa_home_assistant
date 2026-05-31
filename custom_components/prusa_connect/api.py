"""Prusa Connect / PrusaLink API client.

Supports two connection modes:
- Local (PrusaLink): connects directly to printer on LAN via X-Api-Key header
- Cloud (Prusa Connect): connects to connect-mobile-api.prusa3d.com via Bearer JWT
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
    """Client for Prusa Connect cloud API (mobile API)."""

    def __init__(self, token: str, session: aiohttp.ClientSession) -> None:
        self._token = token
        self._session = session
        self._base_url = PRUSA_CONNECT_CLOUD_API

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self._base_url}{path}"
        try:
            async with self._session.request(method, url, headers=self._headers, **kwargs) as resp:
                if resp.status in (401, 403):
                    raise PrusaConnectAuthError("Invalid or expired token")
                if resp.status == 204:
                    return None
                resp.raise_for_status()
                return await resp.json()
        except aiohttp.ClientError as err:
            raise PrusaConnectError(f"Connection error: {err}") from err

    async def get_printers(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/printers")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("member", data.get("printers", data.get("data", [])))
        return []

    async def get_printer(self, printer_uuid: str) -> dict[str, Any]:
        return await self._request("GET", f"/printers/{printer_uuid}")

    async def get_printer_detail(self, printer_uuid: str) -> dict[str, Any]:
        return await self._request("GET", f"/printers/{printer_uuid}/detail")

    async def get_jobs(self, printer_uuid: str) -> list[dict[str, Any]]:
        try:
            data = await self._request(
                "GET", "/jobs", params={"printer[]": printer_uuid, "printerJobStatus": "current"}
            )
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("member", data.get("jobs", []))
            return []
        except PrusaConnectError:
            return []

    async def validate(self) -> bool:
        try:
            await self.get_printers()
            return True
        except PrusaConnectError:
            return False


class PrusaLinkClient:
    """Client for PrusaLink local API on the printer."""

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
        try:
            async with self._session.get(url, headers=self._headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status in (401, 403):
                    raise PrusaConnectAuthError("Invalid API key")
                if resp.status == 204:
                    return None
                resp.raise_for_status()
                return await resp.json()
        except aiohttp.ClientError as err:
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
            async with self._session.get(url, headers=self._headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.read()
                return None
        except aiohttp.ClientError:
            return None

    async def validate(self) -> bool:
        try:
            await self.get_version()
            return True
        except PrusaConnectError:
            return False
