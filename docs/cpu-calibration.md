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

## Signed-in browser validation (2026-10-20)

User signed into a visible Playwright Chromium session and opened Malone serial Q3AA-2LQA-AL24, MR45 firmware MR 31.1.8. Publicly rendered Device Health CPU graph/tooltips expose rounded percentages and HH:mm timestamps, not native sample seconds. Browser timezone America/New_York. Nine unique same-minute archive/UI pairs initially suggested raw/(1000*cores) as a closer display approximation (median error 0.176 percentage points, maximum 0.528) than raw/1000 or raw/(1000*cores)*100. This does not prove core normalization: the tested device has four cores and a narrow 7–9% range. Do not activate thresholds from this preliminary result.

`scripts/cpu-dashboard-observer.js` runs in an authorized signed-in Playwright context: it opens a separate observation tab, refreshes every five minutes, reads the last 15 visible CPU tooltips, checks device serial and writes protected JSONL. It stops scheduling after 24 hours or when the tab closes. Browser/process/login must remain available. No password, cookie or storage-state export; no private dashboard endpoints. Failed reads append explicit errors rather than successful samples.

`scripts/compare-cpu-dashboard.py --ui-jsonl <file> --output <json>` uses the workspace credential-resolving remote helper to read the controller CPU archive via SELECT-only SQLite. It pairs by serial and a unique same displayed minute in the recorded timezone, handles midnight rollover, skips ambiguous minute matches and deduplicates repeated native source observations. These are explicitly approximate UI-time matches, separate from the exact-timestamp CSV importer. Keep provenance and compare only equivalent chart windows. Optional observer callback runs this comparison after every successful browser capture. Results are diagnostics; no automatic formula adoption, capacity state or threshold changes.

Initial collection was started for 24 hours on the current signed-in browser for Malone. Add representative MR33/MR36 observations through their actual dashboard pages before accepting a mapping. Stop by clearing the returned timer or closing its dedicated observation tab. If login expires, sign-in is user handled; do not enter credentials automatically. Local observation JSONL/comparison files live outside Git under the protected task-state directory, with report copies under client outputs.

Initial cross-model checkpoint: 10 unique minute-aligned samples each for MR45 Q3AA-2LQA-AL24, MR33 Q2PD-39TK-UM7P (MR 30.7.1), and MR36 Q3AJ-FEKS-DPKJ (MR 32.2.4). Candidate raw/(1000*cores) median absolute errors were 0.168, 0.328 and 0.240 percentage points respectively; maximum errors 0.528, 0.480 and 0.544. All tested APs report four cores, so dependence on core count versus a model-independent divisor of 4000 is not identified. Three signed-in observers now run every five minutes, with read-only archive comparison after each successful capture, for 24 hours ending approximately 2026-10-21 00:36 America/New_York. Browser/login must remain available; no permanent session export. No formula or thresholds enabled.
