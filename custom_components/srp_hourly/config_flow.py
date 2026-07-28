"""Configuration flow for SRP Hourly Usage."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.util import dt as dt_util

from .const import CONF_ACCOUNT_ID, CONF_TIME_OF_USE, DEFAULT_TIME_OF_USE, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def _validate_input(hass, data: dict[str, Any]) -> None:
    """Confirm that SRP accepts the supplied credentials."""
    from srpenergy.client import SrpEnergyClient

    def _fetch() -> None:
        client = SrpEnergyClient(
            data[CONF_ACCOUNT_ID], data[CONF_USERNAME], data[CONF_PASSWORD]
        )
        yesterday = dt_util.now() - timedelta(days=1)
        client.usage(
            yesterday.replace(hour=0, minute=0, second=0, microsecond=0),
            yesterday.replace(hour=23, minute=59, second=59, microsecond=0),
            data[CONF_TIME_OF_USE],
        )

    await hass.async_add_executor_job(_fetch)


class SrpHourlyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SRP Hourly Usage."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial configuration step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_ACCOUNT_ID])
            self._abort_if_unique_id_configured()
            try:
                await _validate_input(self.hass, user_input)
            except Exception:  # The upstream client has several error types.
                _LOGGER.debug("Unable to validate SRP credentials", exc_info=True)
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(
                    title=f"SRP Hourly ({user_input[CONF_ACCOUNT_ID][-4:]})",
                    data=user_input,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_ACCOUNT_ID): str,
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Optional(
                    CONF_TIME_OF_USE, default=DEFAULT_TIME_OF_USE
                ): bool,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
