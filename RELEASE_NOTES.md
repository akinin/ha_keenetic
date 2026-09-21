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

## Fixed

- Discover Ethernet ports on routers that report flat port objects, including KN-3812, and address port statistics and switch commands by physical interface ID. Port switches now reflect administrative enablement instead of cable link status when the router reports it.
- Send the required JSON body when requesting firmware components, and retain the last valid firmware versions if the router temporarily returns incomplete data.
- Give storage usage and storage usage percentage distinct translated names for newly created entities. Existing entity IDs are preserved to avoid breaking automations.
- Prevent SSDP rediscovery from creating duplicate config entries. Existing config-entry and entity unique IDs are preserved while a verified router can follow a changed address.
