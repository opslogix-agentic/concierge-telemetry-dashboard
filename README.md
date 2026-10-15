# Concierge Telemetry Dashboard

Django 5.2 dashboard for Cerebral Palsy of the North Country. Internal URL: `http://10.1.96.3/telemetry/` (or controller hostname). Separate Django login; change password via the header. All authenticated dashboard users can view this client's inventory. No public signup, inventory editing or monitoring acknowledgement actions.

## What it shows

Location-grouped devices with search/filter by hostname, IP, model, serial and alert status. Device pages include identity/software/uptime, collector assignment, interfaces, addresses, allowed VLANs, stack members, inventory power/fans/temperature, persisted Icinga host/service results, and live controller CPU/memory/environment health. Missing results and source failures show UNKNOWN, never inferred healthy. Stale telemetry is labeled using the fast-health snapshot timestamp, independently of hourly inventory. Snapshot access is read-only under the existing telemetry service user. Acknowledgement/downtime do not hide faults.

Icinga database soft state is the displayed current persisted result, with hard state, output, overdue/ack/downtime and state update timestamp on details. IcingaDB does not necessarily update timestamps on every unchanged check; these timestamps are not heartbeats. Live controller health is fetched separately on device detail. Existing sensor inventory tables can contain older values; live health is labeled distinctly. No auto-refresh during inspection; use Refresh or reload.

## Architecture

Browser → existing Apache :80 `/telemetry/` → HAProxy `127.0.0.1:8082` → Gunicorn/Django `127.0.0.1:8081`.

The original HAProxy service loaded only its base config, with no frontend listeners. Existing `/etc/haproxy/conf.d/services.cfg` was unused, references a missing certificate, and conflicts with Apache :80; do not activate it wholesale. A dedicated systemd drop-in loads only the dashboard config alongside the existing base. All other Apache paths and the telemetry API :8080 remain as configured.

MariaDB `concierge_dashboard` stores Django auth/sessions/migrations only. Inventory is restricted to the CP North tenant UUID. Separate SELECT-only account reads `prod_telemetry` inventory and four IcingaDB tables. Inventory has no Django managed models; database router disallows migrations to telemetry/icinga. Controller health API uses a local, tenant-scoped monitor token. No credentials in Git. Internal HTTP is used because no DNS/TLS certificates are available; use only the trusted internal network/VPN.

## Deployment

Commit and push first; pull on controller as telemetry. Production checkout `/opt/telemetry/concierge-telemetry-dashboard`; venv `/opt/telemetry/dashboard-venv`. Install Python dependencies from requirements.lock.txt (generated from tested environment), with Python development headers, mysqlclient native prerequisites and pkg-config. Create venv separately from checkout, owned by telemetry.

Run `sudo python3 deploy/install.py` from the pulled production checkout. Installer creates dedicated DB accounts/config once, migrates only dashboard DB, collects static assets, creates initial cchavez account once, validates proxy config and installs/enables service. Existing account passwords are never reset. Secrets are in `/etc/concierge-telemetry-dashboard/dashboard.env` and `monitor.token` (root:telemetry 0640); bootstrap admin credential is root-only. Copy bootstrap login to workspace secrets; do not paste it into logs. Installer preserves overwritten managed config files under `/var/backups/concierge-dashboard/`.

Check `systemctl status concierge-telemetry-dashboard haproxy apache2`; `curl http://127.0.0.1:8082/telemetry/healthz/`; unauthenticated overview must redirect to login. Test login, all locations/details and static CSS through Apache. Dashboard deployment must not restart collector/controller/Icinga.

## Development and tests

Tests use isolated SQLite for auth and mock inventory/monitoring; production uses MariaDB. `python manage.py test --settings=dashboard.test_settings`. Production integration tests must also read all live inventory categories, check least-privilege grants, authenticate through the proxy and confirm a known CRITICAL power alert. `python manage.py check --deploy` reports expected internal-HTTP TLS warnings; do not suppress them as if HTTPS were enabled.

## Rollback

Stop/disable concierge-telemetry-dashboard, run `a2disconf concierge-dashboard`, validate and reload Apache. Remove only `/etc/systemd/system/haproxy.service.d/concierge-dashboard.conf`, daemon-reload and restart HAProxy to return to the original base configuration. Keep the new dashboard DB and configuration for investigation. Application updates roll back to a prior Git revision via the repo; do not edit production source. Existing telemetry and Icinga data are read-only and unchanged by deployment.
