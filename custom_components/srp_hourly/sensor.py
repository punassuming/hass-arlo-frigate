"""Diagnostic sensors for SRP Hourly Usage."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import SrpHourlyCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the SRP Hourly diagnostic sensors."""
    coordinator: SrpHourlyCoordinator = entry.runtime_data
    async_add_entities([SrpHourlyUsageSensor(coordinator), SrpHourlyCostSensor(coordinator)])


class SrpHourlySensor(CoordinatorEntity[SrpHourlyCoordinator], SensorEntity):
    """Base class for SRP Hourly diagnostic sensors."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SrpHourlyCoordinator, key: str) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={("srp_hourly", coordinator.entry.entry_id)},
            manufacturer="Salt River Project",
            name=coordinator.entry.title,
        )

    @property
    def extra_state_attributes(self) -> dict[str, str | int] | None:
        """Expose the external statistic IDs for dashboard configuration."""
        if self.coordinator.data is None:
            return None
        return {
            "energy_statistic_id": self.coordinator.energy_statistic_id,
            "cost_statistic_id": self.coordinator.cost_statistic_id,
            "imported_intervals": self.coordinator.data.imported_count,
            "latest_interval_start": self.coordinator.data.start.isoformat(),
        }


class SrpHourlyUsageSensor(SrpHourlySensor):
    """Show the latest SRP interval consumption."""

    _attr_name = "Latest hourly usage"
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR

    def __init__(self, coordinator: SrpHourlyCoordinator) -> None:
        """Initialize the usage sensor."""
        super().__init__(coordinator, "latest_usage")

    @property
    def native_value(self) -> float | None:
        """Return the most recently imported hourly usage."""
        return None if self.coordinator.data is None else self.coordinator.data.energy_kwh


class SrpHourlyCostSensor(SrpHourlySensor):
    """Show the latest SRP interval cost."""

    _attr_name = "Latest hourly cost"
    _attr_device_class = SensorDeviceClass.MONETARY

    def __init__(self, coordinator: SrpHourlyCoordinator) -> None:
        """Initialize the cost sensor."""
        super().__init__(coordinator, "latest_cost")
        self._attr_native_unit_of_measurement = coordinator.hass.config.currency

    @property
    def native_value(self) -> float | None:
        """Return the most recently imported hourly cost."""
        return None if self.coordinator.data is None else self.coordinator.data.cost
