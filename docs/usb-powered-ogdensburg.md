# USB-powered Ogdensburg sensor

Customer confirmed 05-Ogdensburg / Q3CA-ZNNL-LJPD uses USB power on 2026-10-22. Remove only its Icinga battery service and corresponding notifications. Keep temperature and sensor-freshness monitoring, limits and alert routes active. The dashboard omits the battery live check/card.

Canonical non-secret policy is telemetry-controller/config/meraki-device-monitoring-overrides.json, scoped by tenant UUID and serial. The controller treats this battery check as not applicable and excludes USB sensors from depleted-battery temperature suppression. Thus zero/missing battery cannot conceal genuine temperature or data-loss problems on externally powered hardware. The dashboard reads the same controller-owned policy file on this shared host; no duplicate policy source, new credentials or database migration. Client devices.yaml records USB power and selected checks.

Deploy through Git push/pull, controller policy/evaluator first, dashboard consumer next and validated Icinga host configuration reload. Six other battery services, Malone depleted-battery behavior and other environmental checks remain unchanged. Meraki organization-wide payloads may still contain battery fields; those do not create active checks. Preserve history. Roll back via repository revert and corresponding client inventory note only if power-source requirements change.
