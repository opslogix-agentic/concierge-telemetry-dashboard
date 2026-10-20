# CPU telemetry freshness and dashboard calibration

The existing cpu-load resource and Icinga service identity are retained for history/compatibility. Its displayed label is CPU telemetry freshness. OK means a valid CPU integer/core count with source age <=1800 seconds and successful collection age <=900 seconds; it does not grade CPU capacity. Stale, future, missing and malformed readings remain UNKNOWN. No percentage conversion, load thresholds or notifications are activated.

## Periodic source history

Install the repository deploy/concierge-cpu-calibration.service and .timer under /etc/systemd/system; enable/start the timer. Every five minutes, archive the current tenant-scoped MR CPU snapshots already ingested from the Meraki API. This adds no vendor API calls. Records deduplicate by integration, serial and native source timestamp. Samples are retained for 30 days in /var/lib/concierge-cpu-calibration/samples.sqlite3 (telemetry, directory 0700, database 0600). Capture raw value, core count, model, cloud name, collection and observation times. This records snapshots observed by the sampler, not guaranteed complete historical API series. Failed/stale source observations are not treated as calibration samples.

## Dashboard reference observations

No dashboard UI session was available at initial setup; API credentials do not grant browser login. Dashboard-side automated collection is pending browser access. Do not claim API sampling is an API/dashboard comparison. Obtain a signed-in browser and read only Device Health > System Resources > CPU graph/tooltips for MR33, MR36 and MR45. Record exact UTC observation timestamps, displayed value and unit, graph aggregation/window and model/firmware; preserve screenshot/export references. Do not scrape private dashboard endpoints or invent reference values.

Use several independent intervals and devices for each model, including low and higher natural load; do not deliberately stress production. Verify the API and UI use the same five-minute aggregation and timestamp interpretation. Rounded dashboard timestamps must first be reconciled with actual source observations; the importer deliberately requires exact matched timestamps to avoid accidental pairing.

CSV headers:

```
integration_id,serial,observed_at,dashboard_value,unit,provenance
```

unit must be percent or load-average. provenance identifies the actual UI/export artifact and aggregation/window. Never enter guessed values. Import/compare with:

```
/opt/telemetry/dashboard-venv/bin/python manage.py cpu_calibration --database /var/lib/concierge-cpu-calibration/samples.sqlite3 --dashboard-csv /protected/path/dashboard-observations.csv
```

Run as telemetry with the existing dashboard environment loaded. The command compares raw/1000 for a load-average display, and raw/1000 plus raw/(1000*cores)*100 for a percent display. Reports counts and median/maximum absolute error separately by model/unit. These are hypotheses only, not vendor specifications. A consistent empirical fit must hold on independent observations across models and be checked against rounding/window behavior; small sample counts or one low-load match are insufficient. No formula is automatically adopted or clipped at 100, and normalized Unix load is not labeled busy-time CPU utilization. If no stable mapping emerges, keep freshness plus raw diagnostic data.

Disable/stop the timer to stop archival; preserve samples for review. Existing cloud polling and monitoring continue independently. Never commit sample archives or dashboard exports to Git.
