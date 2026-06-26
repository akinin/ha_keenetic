# v2.1.3

Sensor selection update for the Keenetic Router integration.

## Added

- Added a Sensors section to integration options.
- Sensor groups can now be enabled or disabled:
  - Router diagnostics
  - Interface traffic
  - Wi-Fi radio
  - Storage
  - Mesh
- Disabled sensor groups are removed from the Home Assistant entity registry after saving options.

## Notes

Existing installations keep all sensor groups enabled by default.
