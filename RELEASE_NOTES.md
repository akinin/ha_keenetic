# v2.1.2

Bugfix release for the Keenetic Router integration.

## Fixed

- Fixed sensor platform setup when Keenetic returns USB/media partitions as a dictionary instead of a list.
- Restored router diagnostic sensors that could become unavailable after the media diagnostics update.

## Notes

This release supersedes `v2.1.1`. If diagnostics such as CPU load, memory, uptime, hostname, domain name, WAN IP, or Wi-Fi clients are unavailable, update to this version and restart Home Assistant.
