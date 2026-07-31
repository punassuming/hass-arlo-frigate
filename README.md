# SRP Hourly Usage for Home Assistant

[![HACS][hacs-badge]][hacs]
[![Add to HACS][hacs-add-badge]][hacs-add]
[![Add integration][config-flow-badge]][config-flow]

This custom integration imports SRP's completed hourly electricity intervals as
Home Assistant external statistics. It is designed to complement, not replace,
the built-in **SRP Energy** integration, which aggregates SRP's hourly API data
into daily totals.

## Installation

### HACS

Use the **Add to HACS** button above, then select **Download** in HACS. Restart
Home Assistant after the download completes.

### Manual

1. Copy `custom_components/srp_hourly` to your Home Assistant configuration
   directory.
2. Restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration → SRP Hourly Usage**.
4. Enter the same SRP My Account credentials and account ID used by the built-in
   integration. Account-ID dashes are accepted and removed automatically. Enable
   **Time-of-Use price plan** if applicable.

When there is no prior imported data, the integration requests only the current
day and imports every completed hour. If SRP has not published readings yet, it
remembers that date and retries the missing gap on a later poll. Subsequent
syncs run every four hours and request only from the last imported calendar day
through today; the in-progress hour is excluded.

## Optional historical backfill

When the recorder has no hourly readings for the integration, you can request
an intentional historical import from **Developer Tools → Actions**:

```yaml
action: srp_hourly.backfill
data:
  days: 30
```

`days` defaults to `1` and accepts up to `365`. The service makes one SRP API
request for the selected date range, and is rejected after data has been
imported so it cannot accidentally duplicate or recalculate existing statistics.

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

## License

This project is licensed under the GNU General Public License v3.0 or later.
See [LICENSE](LICENSE).

[hacs]: https://hacs.xyz
[hacs-badge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=flat-square
[hacs-add]: https://my.home-assistant.io/redirect/hacs_repository/?owner=punassuming&repository=hass-srp-hourly&category=integration
[hacs-add-badge]: https://my.home-assistant.io/badges/hacs_repository.svg
[config-flow]: https://my.home-assistant.io/redirect/config_flow_start?domain=srp_hourly
[config-flow-badge]: https://my.home-assistant.io/badges/config_flow_start.svg
