# Meraki device display names

Use the device name collected from Meraki Dashboard as the primary visible label. Example: serial Q3AA-2LQA-AL24 is CHC-AP-02-01 - Back Right.

Preserve network_devices IDs/hostnames, Meraki serial identity, Icinga object names and monitoring aliases. These identify polling targets and retain check history even when display names change or duplicate another device name. Devices without a cloud name fall back to inventory hostname.

The telemetry dashboard already reads current names from discovery snapshots; its overview and detail headings now prioritize these names. Icinga uses display_name populated from the current approved discovery snapshot for the 58 existing monitored Meraki hosts. Seven registered devices without active Meraki host objects were not enabled by this change. Future Meraki renames appear in the telemetry dashboard after discovery refresh; Icinga display labels require a corresponding repository configuration update. Notifications remain subject to existing pilot settings.
