"""DataUpdateCoordinator for Prusa Connect."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import PrusaConnectClient, PrusaConnectError, PrusaLinkClient
from .const import (
    CONF_API_KEY,
    CONF_CONNECTION_TYPE,
    CONF_HOST,
    CONF_PRINTER_UUID,
    CONNECTION_TYPE_LOCAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(seconds=30)


class PrusaConnectData:
    """Structured container for printer data."""

    def __init__(self) -> None:
        self.printer_info: dict[str, Any] = {}
        self.status: dict[str, Any] = {}
        self.printer_status: dict[str, Any] = {}
        self.job: dict[str, Any] | None = None
        self.job_file: dict[str, Any] = {}

    @property
    def printer_name(self) -> str:
        return self.printer_info.get("name", self.printer_info.get("hostname", "Prusa Printer"))

    @property
    def printer_type(self) -> str:
        return self.printer_info.get("printer_type", self.printer_info.get("type", ""))

    @property
    def serial_number(self) -> str:
        return self.printer_info.get("serial", self.printer_info.get("serialNumber", ""))

    @property
    def firmware_version(self) -> str:
        return self.printer_info.get("firmware", "")

    @property
    def state(self) -> str:
        s = self.printer_status.get("state", "")
        if not s:
            s = self.status.get("state", self.status.get("printer_state", "UNKNOWN"))
        return str(s).upper()

    @property
    def nozzle_temp(self) -> float | None:
        return self._float("temp_nozzle", "nozzle_temp", "nozzle_temperature")

    @property
    def bed_temp(self) -> float | None:
        return self._float("temp_bed", "bed_temp", "bed_temperature")

    @property
    def nozzle_target_temp(self) -> float | None:
        return self._float("target_nozzle", "temp_nozzle_target", "nozzle_target")

    @property
    def bed_target_temp(self) -> float | None:
        return self._float("target_bed", "temp_bed_target", "bed_target")

    @property
    def progress(self) -> int | None:
        val = self._job_field("progress")
        if val is not None:
            try:
                return int(float(val))
            except (ValueError, TypeError):
                pass
        return None

    @property
    def print_speed(self) -> int | None:
        return self._int("speed", "printing_speed")

    @property
    def flow_factor(self) -> int | None:
        return self._int("flow", "flow_factor")

    @property
    def z_height(self) -> float | None:
        return self._float("axis_z", "pos_z_mm")

    @property
    def fan_hotend(self) -> int | None:
        return self._int("fan_hotend")

    @property
    def fan_print(self) -> int | None:
        return self._int("fan_print")

    @property
    def material(self) -> str | None:
        return self.printer_status.get("material") or self.printer_info.get("material")

    @property
    def project_name(self) -> str | None:
        if self.job_file:
            return self.job_file.get("display_name", self.job_file.get("name"))
        return self.printer_status.get("project_name")

    @property
    def time_remaining(self) -> int | None:
        val = self._job_field("time_remaining")
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                pass
        return None

    @property
    def time_printing(self) -> int | None:
        val = self._job_field("time_printing")
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                pass
        return None

    @property
    def is_printing(self) -> bool:
        return self.state in ("PRINTING", "BUSY")

    @property
    def is_online(self) -> bool:
        return self.state not in ("OFFLINE", "UNKNOWN", "")

    @property
    def camera_url(self) -> str | None:
        return self.printer_info.get("camera_url")

    def _float(self, *keys: str) -> float | None:
        for k in keys:
            for src in (self.printer_status, self.status):
                val = src.get(k)
                if val is not None:
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        pass
        return None

    def _int(self, *keys: str) -> int | None:
        for k in keys:
            for src in (self.printer_status, self.status):
                val = src.get(k)
                if val is not None:
                    try:
                        return int(val)
                    except (ValueError, TypeError):
                        pass
        return None

    def _job_field(self, key: str) -> Any:
        if self.job:
            val = self.job.get(key)
            if val is not None:
                return val
        return self.printer_status.get(key, self.status.get(key))


class PrusaConnectCoordinator(DataUpdateCoordinator[PrusaConnectData]):
    """Coordinator to manage fetching Prusa Connect data."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._connection_type = entry.data.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_LOCAL)
        session = async_get_clientsession(hass)

        if self._connection_type == CONNECTION_TYPE_LOCAL:
            self._local_client = PrusaLinkClient(
                entry.data[CONF_HOST], entry.data[CONF_API_KEY], session
            )
            self._cloud_client = None
            self._printer_uuid = None
        else:
            self._local_client = None
            self._cloud_client = PrusaConnectClient(entry.data[CONF_API_KEY], session)
            self._printer_uuid = entry.data[CONF_PRINTER_UUID]

        self.printer_data = PrusaConnectData()

        interval = timedelta(
            seconds=entry.options.get("scan_interval", 30)
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=interval,
            config_entry=entry,
        )

    async def _async_update_data(self) -> PrusaConnectData:
        try:
            if self._local_client:
                await self._update_local()
            else:
                await self._update_cloud()
            return self.printer_data
        except PrusaConnectError as err:
            raise UpdateFailed(f"Error communicating with Prusa: {err}") from err

    async def _update_local(self) -> None:
        client = self._local_client
        assert client is not None

        try:
            info = await client.get_info()
            self.printer_data.printer_info = info
        except PrusaConnectError:
            pass

        status = await client.get_status()
        self.printer_data.status = status
        self.printer_data.printer_status = status.get("printer", status)

        job_data = status.get("job")
        if job_data:
            self.printer_data.job = job_data
        else:
            job = await client.get_job()
            self.printer_data.job = job

        if self.printer_data.job:
            self.printer_data.job_file = self.printer_data.job.get("file", {})

    async def _update_cloud(self) -> None:
        client = self._cloud_client
        uuid = self._printer_uuid
        assert client is not None and uuid is not None

        printer = await client.get_printer(uuid)
        self.printer_data.printer_info = printer
        self.printer_data.printer_status = printer
        self.printer_data.status = printer

        jobs = await client.get_jobs(uuid)
        if jobs:
            self.printer_data.job = jobs[0]
            self.printer_data.job_file = jobs[0].get("file", {})
        else:
            self.printer_data.job = None
            self.printer_data.job_file = {}
