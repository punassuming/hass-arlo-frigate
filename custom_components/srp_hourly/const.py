"""Constants for the SRP Hourly Usage integration."""

from datetime import timedelta

DOMAIN = "srp_hourly"

CONF_ACCOUNT_ID = "account_id"
CONF_TIME_OF_USE = "time_of_use"
DEFAULT_TIME_OF_USE = False
# SRP makes up to three years of account history available online. This is only
# used for the first import; subsequent refreshes request new intervals only.
INITIAL_HISTORY_LOOKBACK_DAYS = 365 * 3
UPDATE_INTERVAL = timedelta(hours=4)

STATISTIC_ENERGY_SUFFIX = "energy"
STATISTIC_COST_SUFFIX = "cost"


def normalize_account_id(account_id: str) -> str:
    """Return an SRP account ID without display separators."""
    return account_id.replace("-", "")
