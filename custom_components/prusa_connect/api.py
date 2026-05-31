"""Prusa Connect / PrusaLink API client.

Supports two connection modes:

- **Local (PrusaLink)** — connects directly to the printer on the LAN using the
  ``X-Api-Key`` header. This is the documented, reliable path.

- **Cloud (Prusa Connect)** — connects to ``connect.prusa3d.com`` using a Prusa
  *account* OAuth2 access token (Authorization-Code + PKCE), exactly like
  PrusaSlicer/OrcaSlicer. The per-printer "API key" shown in Prusa Connect does
  **not** authenticate the cloud data endpoints — those require a Bearer token.

OAuth2 details verified against PrusaSlicer source:
  - authorize: ``{account}/o/authorize/`` (PKCE S256, scope ``basic_info``,
    redirect ``prusaslicer://login``)
  - token: ``{account}/o/token/`` (``authorization_code`` then ``refresh_token``)
  - data: ``{connect}/slicer/v1/printers`` and ``{connect}/app/printers/{uuid}``
    with ``Authorization: Bearer <access_token>``
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
from typing import Any, Awaitable, Callable
from urllib.parse import urlencode

import aiohttp

from .const import (
    PRUSA_ACCOUNT_API,
    PRUSA_CONNECT_CLOUD_API,
    PRUSA_OAUTH_AUTHORIZE_PATH,
    PRUSA_OAUTH_CLIENT_ID,
    PRUSA_OAUTH_REDIRECT_URI,
    PRUSA_OAUTH_SCOPE,
    PRUSA_OAUTH_TOKEN_PATH,
)

_LOGGER = logging.getLogger(__name__)


class PrusaConnectError(Exception):
    """Base exception for Prusa Connect API errors."""


class PrusaConnectAuthError(PrusaConnectError):
    """Authentication error (token invalid/expired and refresh failed)."""


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------

def generate_pkce_pair() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) for an OAuth2 PKCE (S256) flow.

    RFC 7636: verifier is 43-128 chars from the unreserved set; the challenge is
    base64url(sha256(verifier)) with padding stripped.
    """
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def build_authorize_url(code_challenge: str, language: str = "en") -> str:
    """Build the Prusa account OAuth2 authorize URL."""
    params = {
        "embed": "1",
        "client_id": PRUSA_OAUTH_CLIENT_ID,
        "response_type": "code",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "scope": PRUSA_OAUTH_SCOPE,
        "redirect_uri": PRUSA_OAUTH_REDIRECT_URI,
        "language": language[:2] if language else "en",
    }
    return f"{PRUSA_ACCOUNT_API}{PRUSA_OAUTH_AUTHORIZE_PATH}?{urlencode(params)}"


def extract_code(raw: str) -> str:
    """Extract the authorization code from a pasted value.

    Accepts either a bare code, or the full redirect URL the browser lands on
    (``prusaslicer://login?code=...&...``).
    """
    raw = raw.strip()
    if "code=" in raw:
        # Pull the code query parameter out of a pasted redirect URL.
        after = raw.split("code=", 1)[1]
        return after.split("&", 1)[0].strip()
    return raw


# ---------------------------------------------------------------------------
# Cloud client (OAuth2 Bearer)
# ---------------------------------------------------------------------------

class PrusaConnectClient:
    """Client for the Prusa Connect cloud API using an account OAuth2 token.

    Handles transparent access-token refresh. When tokens are refreshed, the
    optional ``token_updated`` callback is invoked so the caller can persist the
    new tokens to the config entry.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        access_token: str | None = None,
        refresh_token: str | None = None,
        token_updated: Callable[[str, str], Awaitable[None]] | None = None,
    ) -> None:
        self._session = session
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._token_updated = token_updated

    @property
    def access_token(self) -> str | None:
        return self._access_token

    @property
    def refresh_token(self) -> str | None:
        return self._refresh_token

    # -- OAuth token exchange ------------------------------------------------

    async def async_exchange_code(self, code: str, code_verifier: str) -> tuple[bool, str]:
        """Exchange an authorization code for tokens. Returns (ok, detail)."""
        body = {
            "code": code,
            "client_id": PRUSA_OAUTH_CLIENT_ID,
            "grant_type": "authorization_code",
            "redirect_uri": PRUSA_OAUTH_REDIRECT_URI,
            "code_verifier": code_verifier,
        }
        return await self._token_request(body, "authorization_code")

    async def async_login_password(
        self, username: str, password: str
    ) -> tuple[bool, str]:
        """Log in directly with a Prusa account email + password (ROPC).

        Returns (ok, detail). This is the convenient path: no browser, no
        copy-paste. It will not work for accounts with two-factor auth (the
        password grant can't present a 2FA challenge) — those should use the
        browser flow instead.
        """
        body = {
            "grant_type": "password",
            "client_id": PRUSA_OAUTH_CLIENT_ID,
            "username": username,
            "password": password,
            "scope": PRUSA_OAUTH_SCOPE,
        }
        ok, detail = await self._token_request(body, "password")
        if not ok and "invalid_grant" in detail.lower():
            # Friendlier message for the most common failure.
            detail = (
                "Incorrect email/password, or this account uses two-factor "
                "authentication (which requires the browser login instead)."
            )
        return ok, detail

    async def async_refresh_token(self) -> tuple[bool, str]:
        """Refresh the access token. Returns (ok, detail)."""
        if not self._refresh_token:
            return False, "No refresh token stored — please re-authenticate."
        body = {
            "grant_type": "refresh_token",
            "client_id": PRUSA_OAUTH_CLIENT_ID,
            "refresh_token": self._refresh_token,
        }
        return await self._token_request(body, "refresh_token")

    async def _token_request(self, body: dict[str, str], label: str) -> tuple[bool, str]:
        url = f"{PRUSA_ACCOUNT_API}{PRUSA_OAUTH_TOKEN_PATH}"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        _LOGGER.warning("Prusa Connect: OAuth %s token request to %s", label, url)
        try:
            async with self._session.post(
                url, data=body, headers=headers,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                text = await resp.text()
                if resp.status != 200:
                    detail = self._error_detail(text)
                    msg = f"Token request failed (HTTP {resp.status}): {detail}"
                    _LOGGER.warning("Prusa Connect: %s", msg)
                    return False, msg
                data = json.loads(text)
                access = data.get("access_token")
                refresh = data.get("refresh_token", self._refresh_token)
                if not access:
                    return False, "Token response did not include an access_token."
                self._access_token = access
                self._refresh_token = refresh
                if self._token_updated:
                    await self._token_updated(access, refresh)
                _LOGGER.warning("Prusa Connect: OAuth %s succeeded", label)
                return True, "Authenticated with Prusa account."
        except (aiohttp.ClientError, json.JSONDecodeError) as err:
            msg = f"Token request error: {err}"
            _LOGGER.warning("Prusa Connect: %s", msg)
            return False, msg

    @staticmethod
    def _error_detail(text: str) -> str:
        try:
            data = json.loads(text)
            return (
                data.get("error_description")
                or data.get("message")
                or data.get("error")
                or text[:200]
            )
        except (json.JSONDecodeError, AttributeError):
            return text[:200]

    # -- Authenticated data requests ----------------------------------------

    async def _request(
        self, method: str, path: str, *, _retried: bool = False, **kwargs: Any
    ) -> Any:
        """Make a Bearer-authenticated request, refreshing the token on 401."""
        if not self._access_token:
            raise PrusaConnectAuthError("No access token — please authenticate.")

        url = f"{PRUSA_CONNECT_CLOUD_API}{path}"
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
        }
        try:
            async with self._session.request(
                method, url, headers=headers,
                timeout=aiohttp.ClientTimeout(total=20), **kwargs,
            ) as resp:
                text = await resp.text()
                if resp.status in (401, 403) and not _retried:
                    _LOGGER.warning(
                        "Prusa Connect: %s %s -> HTTP %s, attempting token refresh",
                        method, path, resp.status,
                    )
                    ok, detail = await self.async_refresh_token()
                    if not ok:
                        raise PrusaConnectAuthError(detail)
                    return await self._request(method, path, _retried=True, **kwargs)
                if resp.status in (401, 403):
                    raise PrusaConnectAuthError(
                        f"Auth failed (HTTP {resp.status}) for {method} {path}"
                    )
                if resp.status >= 400:
                    raise PrusaConnectError(
                        f"HTTP {resp.status} for {method} {path}: {text[:200]}"
                    )
                if not text.strip():
                    return None
                return json.loads(text)
        except aiohttp.ClientError as err:
            raise PrusaConnectError(f"Connection error: {err}") from err
        except json.JSONDecodeError as err:
            raise PrusaConnectError(f"Invalid JSON from {path}: {err}") from err

    async def get_image(self, url: str, *, _retried: bool = False) -> bytes | None:
        """Fetch raw image bytes (e.g. the job preview) with Bearer auth.

        ``url`` may be absolute (job_info.preview_url) or a /app/... relative path.
        """
        if not self._access_token:
            return None
        full = url if url.startswith("http") else f"{PRUSA_CONNECT_CLOUD_API}{url}"
        headers = {"Authorization": f"Bearer {self._access_token}"}
        try:
            async with self._session.get(
                full, headers=headers, timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                if resp.status in (401, 403) and not _retried:
                    ok, _ = await self.async_refresh_token()
                    if ok:
                        return await self.get_image(url, _retried=True)
                    return None
                if resp.status == 200:
                    return await resp.read()
                _LOGGER.debug("Prusa Connect preview %s -> HTTP %s", full, resp.status)
                return None
        except aiohttp.ClientError as err:
            _LOGGER.debug("Prusa Connect preview fetch failed: %s", err)
            return None

    async def validate(self) -> tuple[bool, str]:
        """Validate the current token by listing printers."""
        try:
            printers = await self.get_printers()
            count = len(printers)
            return True, f"Authenticated — found {count} printer(s) on the account."
        except PrusaConnectAuthError as err:
            return False, f"Authentication failed: {err}"
        except PrusaConnectError as err:
            return False, f"Connection failed: {err}"

    async def get_printers(self) -> list[dict[str, Any]]:
        """Return the list of printers on the account."""
        data = await self._request("GET", "/slicer/v1/printers")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("printers", "member", "data", "result"):
                if isinstance(data.get(key), list):
                    return data[key]
            return [data]
        return []

    async def get_printer(self, printer_uuid: str) -> dict[str, Any]:
        """Return detailed data for a single printer."""
        return await self._request("GET", f"/app/printers/{printer_uuid}")

    async def get_jobs(self, printer_uuid: str) -> list[dict[str, Any]]:
        """Return jobs for a printer (best-effort across known endpoints)."""
        for path in (
            f"/app/printers/{printer_uuid}/job",
            f"/app/printers/{printer_uuid}/jobs",
        ):
            try:
                data = await self._request("GET", path)
            except PrusaConnectError:
                continue
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                if "id" in data or "state" in data:
                    return [data]
                for key in ("member", "jobs", "data"):
                    if isinstance(data.get(key), list):
                        return data[key]
        return []


# ---------------------------------------------------------------------------
# Local client (PrusaLink, X-Api-Key)
# ---------------------------------------------------------------------------

class PrusaLinkClient:
    """Client for the PrusaLink local API on the printer (X-Api-Key)."""

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
                return await resp.json()
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

    async def get_image(self, path: str) -> bytes | None:
        """Fetch raw image bytes from a printer-relative path (e.g. a thumbnail)."""
        url = f"{self._host}{path}"
        try:
            async with self._session.get(
                url, headers=self._headers, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status == 200:
                    return await resp.read()
                _LOGGER.debug("PrusaLink thumbnail %s -> HTTP %s", url, resp.status)
                return None
        except aiohttp.ClientError as err:
            _LOGGER.debug("PrusaLink thumbnail fetch failed for %s: %s", url, err)
            return None

    async def _command(self, method: str, path: str) -> None:
        """Send a state-changing command (expects HTTP 2xx/204)."""
        url = f"{self._host}{path}"
        _LOGGER.debug("PrusaLink command: %s %s", method, url)
        try:
            async with self._session.request(
                method, url, headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status in (401, 403):
                    raise PrusaConnectAuthError(f"Invalid API key (HTTP {resp.status})")
                if resp.status >= 400:
                    body = await resp.text()
                    raise PrusaConnectError(
                        f"Command {method} {path} failed (HTTP {resp.status}): "
                        f"{body[:200]}"
                    )
        except aiohttp.ClientError as err:
            raise PrusaConnectError(f"Connection error: {err}") from err

    async def pause_job(self, job_id: int) -> None:
        await self._command("PUT", f"/api/v1/job/{job_id}/pause")

    async def resume_job(self, job_id: int) -> None:
        await self._command("PUT", f"/api/v1/job/{job_id}/resume")

    async def stop_job(self, job_id: int) -> None:
        await self._command("DELETE", f"/api/v1/job/{job_id}")

    async def validate(self) -> tuple[bool, str]:
        """Validate the API key against the printer."""
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
