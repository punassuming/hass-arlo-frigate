"""Fetch and import SRP interval data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import logging
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.components.recorder.models import StatisticMeanType
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .const import (
    CONF_ACCOUNT_ID,
    CONF_TIME_OF_USE,
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
        # Statistic IDs permit only lowercase letters, numbers, and single
        # underscores. Slugify also handles config entry IDs from older and
        # newer Home Assistant versions without relying on their format.
        statistic_key = slugify(entry.entry_id)
        self.energy_statistic_id = f"{DOMAIN}:{statistic_key}_{STATISTIC_ENERGY_SUFFIX}"
        self.cost_statistic_id = f"{DOMAIN}:{statistic_key}_{STATISTIC_COST_SUFFIX}"

    async def _async_update_data(self) -> ImportedInterval | None:
        """Fetch completed intervals and add only the new ones."""
        state = await self._store.async_load() or {}
        latest_start = self._parse_stored_start(state.get("latest_start"))
        backfill_start = self._parse_stored_day(state.get("backfill_start"))
        energy_sum = float(state.get("energy_sum", 0))
        cost_sum = float(state.get("cost_sum", 0))

        # Do not import the in-progress hour, but retain all prior hours from
        # today so a newly added integration immediately backfills them.
        now = dt_util.now().astimezone(self._local_tz)
        current_hour_start = now.replace(minute=0, second=0, microsecond=0)
        query_end_day = now.date()
        if latest_start is None:
            # The hourly endpoint accepts date ranges, not individual hours.
            # Start with today's smallest possible range and retain this date
            # if SRP has not yet published any readings to retry only the gap.
            query_start = backfill_start or query_end_day
            if backfill_start is None:
                state = {**state, "backfill_start": query_start.isoformat()}
                await self._store.async_save(state)
        else:
            query_start = latest_start.astimezone(self._local_tz).date()

        if query_start > query_end_day:
            return self.data

        try:
            usage = await self.hass.async_add_executor_job(
                self._fetch_usage, query_start, query_end_day
            )
        except Exception as err:
            raise UpdateFailed(f"Error fetching SRP hourly usage: {err}") from err

        intervals = self._parse_intervals(usage, current_hour_start)
        completed_interval_count = len(intervals)
        if latest_start is not None:
            intervals = [interval for interval in intervals if interval.start > latest_start]

        _LOGGER.info(
            "SRP hourly query %s through %s returned %s interval(s); "
            "%s were completed and %s are new",
            query_start,
            query_end_day,
            len(usage),
            completed_interval_count,
            len(intervals),
        )

        if not intervals:
            _LOGGER.info(
                "No new SRP hourly intervals are available after %s", latest_start
            )
            if latest_start is None:
                await self._store.async_save(
                    {**state, "backfill_start": query_start.isoformat()}
                )
            return self.data

        energy_statistics = []
        cost_statistics = []
        for interval in intervals:
            energy_sum += interval.energy_kwh
            cost_sum += interval.cost
            energy_statistics.append(
                {"start": interval.start, "state": energy_sum, "sum": energy_sum}
            )
            cost_statistics.append(
                {"start": interval.start, "state": cost_sum, "sum": cost_sum}
            )

        async_add_external_statistics(
            self.hass,
            {
                "has_mean": False,
                "has_sum": True,
                "mean_type": StatisticMeanType.NONE,
                "name": f"{self.entry.title} electric consumption",
                "source": DOMAIN,
                "statistic_id": self.energy_statistic_id,
                "unit_class": "energy",
                "unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
            },
            energy_statistics,
        )
        async_add_external_statistics(
            self.hass,
            {
                "has_mean": False,
                "has_sum": True,
                "mean_type": StatisticMeanType.NONE,
                "name": f"{self.entry.title} electric cost",
                "source": DOMAIN,
                "statistic_id": self.cost_statistic_id,
                "unit_class": None,
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

    async def async_start_backfill(self, days: int) -> None:
        """Request an explicit historical import before any data exists."""
        state = await self._store.async_load() or {}
        has_statistics = await self.hass.async_add_executor_job(
            self._has_imported_energy_statistics
        )
        if has_statistics:
            raise HomeAssistantError(
                "Backfill is only available before SRP hourly data is imported"
            )

        if self._parse_stored_start(state.get("latest_start")) is not None:
            _LOGGER.warning(
                "SRP hourly storage reported imported data, but the recorder has no "
                "energy statistics; resetting the stale import checkpoint"
            )
            state = {}

        end_day = dt_util.now().astimezone(self._local_tz).date()
        requested_start = end_day - timedelta(days=days - 1)
        stored_start = self._parse_stored_day(state.get("backfill_start"))
        backfill_start = (
            min(stored_start, requested_start) if stored_start else requested_start
        )
        await self._store.async_save(
            {**state, "backfill_start": backfill_start.isoformat()}
        )
        _LOGGER.info(
            "Starting requested SRP hourly backfill from %s through %s",
            backfill_start,
            end_day,
        )
        await self.async_refresh()

    def _has_imported_energy_statistics(self) -> bool:
        """Return whether the recorder contains this entry's energy statistics."""
        statistics = get_last_statistics(
            self.hass,
            1,
            self.energy_statistic_id,
            False,
            {"state", "sum"},
        )
        return bool(statistics.get(self.energy_statistic_id))

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

    def _parse_intervals(self, usage, current_hour_start) -> list[ImportedInterval]:
        """Convert upstream tuples to sorted intervals before the current hour."""
        intervals: list[ImportedInterval] = []
        for _date, _hour, iso_hour, kwh, cost in usage:
            start = datetime.fromisoformat(iso_hour)
            if start.tzinfo is None:
                start = start.replace(tzinfo=self._local_tz)
            start = start.astimezone(timezone.utc)
            if start >= current_hour_start.astimezone(timezone.utc):
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

    @staticmethod
    def _parse_stored_day(value: str | None) -> date | None:
        """Read an ISO date from persistent storage."""
        return date.fromisoformat(value) if value else None
