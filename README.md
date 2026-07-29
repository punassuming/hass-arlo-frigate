# SRP Hourly Usage for Home Assistant

This custom integration imports SRP's completed hourly electricity intervals as
Home Assistant external statistics. It is designed to complement, not replace,
the built-in **SRP Energy** integration, which aggregates SRP's hourly API data
into daily totals.

## Install

1. Copy `custom_components/srp_hourly` to your Home Assistant configuration
   directory.
2. Restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration → SRP Hourly Usage**.
4. Enter the same SRP My Account credentials and account ID used by the built-in
   integration. Account-ID dashes are accepted and removed automatically. Enable
   **Time-of-Use price plan** if applicable.

The first sync imports up to three years of complete hourly history available
from SRP. Later syncs run every four hours and only import newly completed
intervals. The integration intentionally excludes the current day because SRP
can revise recent readings.

## Hourly dashboard cards

Find the two statistic IDs in the attributes of either **Latest hourly usage**
or **Latest hourly cost**. They have this form:

```text
srp_hourly:<safe-config-entry-id>_energy
srp_hourly:<safe-config-entry-id>_cost
```

Use them directly in a manual card. These are external statistic IDs, not
sensor entity IDs.

```yaml
type: statistics-graph
title: SRP hourly electricity use
entities:
  - srp_hourly:REPLACE_WITH_THE_DISPLAYED_ENERGY_STATISTIC_ID
chart_type: bar
stat_types:
  - change
period: hour
days_to_show: 1
```

For hourly cost, replace the statistic ID with the one ending in `_cost` and
change the title. A new chart is populated only after SRP publishes completed
interval data; it is not live power monitoring.
