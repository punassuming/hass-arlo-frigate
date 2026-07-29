"""Fetch and import SRP interval data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
import logging
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ACCOUNT_ID,
    CONF_TIME_OF_USE,
    DEFAULT_LOOKBACK_DAYS,
    DOMAIN,
    STATISTIC_COST_SUFFIX,
    STATISTIC_ENERGY_SUFFIX,
    UPDATE_INTERVAL,
    normalize_account_id,
)

_LOGGER = logging.getLogger(__name__)
STORAGE_VERSION = 1


@dataclass(frozen=True, slots=True)
class ImportedInterval:
    """The latest successfully imported SRP interval."""

    start: datetime
    energy_kwh: float
    cost: float
    imported_count: int


class SrpHourlyCoordinator(DataUpdateCoordinator[ImportedInterval | None]):
    """Coordinate SRP polling and write each interval to statistics."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.entry = entry
        self._store = Store[dict[str, Any]](
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self._local_tz = ZoneInfo(hass.config.time_zone)
        # Config entry IDs are UUIDs and may contain hyphens, which Home
        # Assistant does not allow in external statistic IDs.
        statistic_key = entry.entry_id.replace("-", "")
        self.energy_statistic_id = f"{DOMAIN}:{statistic_key}_{STATISTIC_ENERGY_SUFFIX}"
        self.cost_statistic_id = f"{DOMAIN}:{statistic_key}_{STATISTIC_COST_SUFFIX}"

    async def _async_update_data(self) -> ImportedInterval | None:
        """Fetch completed intervals and add only the new ones."""
        state = await self._store.async_load() or {}
        latest_start = self._parse_stored_start(state.get("latest_start"))
        energy_sum = float(state.get("energy_sum", 0))
        cost_sum = float(state.get("cost_sum", 0))

        # SRP commonly revises the most recent day for several hours. Import
        # only complete days so a value is not permanently recorded too early.
        today = dt_util.now().astimezone(self._local_tz).date()
        latest_complete_day = today - timedelta(days=1)
        if latest_start is None:
            query_start = latest_complete_day - timedelta(days=DEFAULT_LOOKBACK_DAYS - 1)
        else:
            query_start = latest_start.astimezone(self._local_tz).date()

        if query_start > latest_complete_day:
            return self.data

        try:
            usage = await self.hass.async_add_executor_job(
                self._fetch_usage, query_start, latest_complete_day
            )
        except Exception as err:
            raise UpdateFailed(f"Error fetching SRP hourly usage: {err}") from err

        intervals = self._parse_intervals(usage, latest_complete_day)
        if latest_start is not None:
            intervals = [interval for interval in intervals if interval.start > latest_start]

        if not intervals:
            return self.data

        energy_statistics = []
        cost_statistics = []
        for interval in intervals:
            energy_sum += interval.energy_kwh
            cost_sum += interval.cost
            timestamp = interval.start.timestamp()
            energy_statistics.append(
                {"start": timestamp, "state": energy_sum, "sum": energy_sum}
            )
            cost_statistics.append(
                {"start": timestamp, "state": cost_sum, "sum": cost_sum}
            )

        async_add_external_statistics(
            self.hass,
            {
                "has_mean": False,
                "has_sum": True,
                "name": f"{self.entry.title} electric consumption",
                "source": DOMAIN,
                "statistic_id": self.energy_statistic_id,
                "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
            },
            energy_statistics,
        )
        async_add_external_statistics(
            self.hass,
            {
                "has_mean": False,
                "has_sum": True,
                "name": f"{self.entry.title} electric cost",
                "source": DOMAIN,
                "statistic_id": self.cost_statistic_id,
                "unit_of_measurement": self.hass.config.currency,
            },
            cost_statistics,
        )

        latest = intervals[-1]
        await self._store.async_save(
            {
                "cost_sum": cost_sum,
                "energy_sum": energy_sum,
                "latest_start": latest.start.isoformat(),
            }
        )
        _LOGGER.info("Imported %s SRP hourly intervals through %s", len(intervals), latest.start)
        return ImportedInterval(
            start=latest.start,
            energy_kwh=latest.energy_kwh,
            cost=latest.cost,
            imported_count=len(intervals),
        )

    def _fetch_usage(self, start_day, end_day):
        """Fetch data from the synchronous srpenergy client."""
        from srpenergy.client import SrpEnergyClient

        client = SrpEnergyClient(
            normalize_account_id(self.entry.data[CONF_ACCOUNT_ID]),
            self.entry.data[CONF_USERNAME],
            self.entry.data[CONF_PASSWORD],
        )
        return client.usage(
            datetime.combine(start_day, time.min),
            datetime.combine(end_day, time.max),
            self.entry.data[CONF_TIME_OF_USE],
        )

    def _parse_intervals(self, usage, latest_complete_day) -> list[ImportedInterval]:
        """Convert the upstream tuples to sorted, completed local intervals."""
        intervals: list[ImportedInterval] = []
        for _date, _hour, iso_hour, kwh, cost in usage:
            start = datetime.fromisoformat(iso_hour)
            if start.tzinfo is None:
                start = start.replace(tzinfo=self._local_tz)
            start = start.astimezone(timezone.utc)
            if start.astimezone(self._local_tz).date() > latest_complete_day:
                continue
            intervals.append(
                ImportedInterval(
                    start=start,
                    energy_kwh=float(kwh),
                    cost=float(cost),
                    imported_count=0,
                )
            )
        return sorted(intervals, key=lambda interval: interval.start)

    @staticmethod
    def _parse_stored_start(value: str | None) -> datetime | None:
        """Read an ISO timestamp from persistent storage."""
        return datetime.fromisoformat(value) if value else None
