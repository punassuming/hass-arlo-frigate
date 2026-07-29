"""SRP Hourly Usage integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .coordinator import SrpHourlyCoordinator
from .const import ATTR_DAYS, ATTR_ENTRY_ID, DOMAIN, MAX_BACKFILL_DAYS, SERVICE_BACKFILL

PLATFORMS: list[Platform] = [Platform.SENSOR]
BACKFILL_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_DAYS, default=1): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=MAX_BACKFILL_DAYS)
        ),
        vol.Optional(ATTR_ENTRY_ID): cv.string,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SRP Hourly Usage from a config entry."""
    coordinator = SrpHourlyCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    if not hass.services.has_service(DOMAIN, SERVICE_BACKFILL):

        async def async_handle_backfill(call: ServiceCall) -> None:
            """Run an explicitly requested historical import."""
            entry_id = call.data.get(ATTR_ENTRY_ID)
            if entry_id:
                target_entry = hass.config_entries.async_get_entry(entry_id)
                if target_entry is None or target_entry.domain != DOMAIN:
                    raise HomeAssistantError("SRP Hourly config entry not found")
                entries = [target_entry]
            else:
                entries = [
                    config_entry
                    for config_entry in hass.config_entries.async_entries(DOMAIN)
                    if getattr(config_entry, "runtime_data", None) is not None
                ]

            if len(entries) != 1:
                raise HomeAssistantError(
                    "Specify entry_id when more than one SRP Hourly entry is configured"
                )

            await entries[0].runtime_data.async_start_backfill(call.data[ATTR_DAYS])

        hass.services.async_register(
            DOMAIN,
            SERVICE_BACKFILL,
            async_handle_backfill,
            schema=BACKFILL_SERVICE_SCHEMA,
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an SRP Hourly Usage config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
