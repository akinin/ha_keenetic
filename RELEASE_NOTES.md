# v2.1.4

## Fixed

- Repair legacy saved IPv6 router URLs without square brackets during SSDP rediscovery, preventing invalid-port exceptions without changing config-entry or entity unique IDs (#27).
- Preserve the configured IPv4 or IPv6 address family when the same router advertises both, while still following address changes within that family.
- Compare equivalent IPv6 address spellings consistently and use bracketed IPv6 URLs in new discovery forms.
- Skip malformed saved addresses and SSDP locations without crashing discovery. Preserve the configured scheme, port, credentials and URL path when updating a valid address.
- Allow the shared `pyqrcode` dependency to follow Home Assistant updates, as required by current hassfest validation.

## Added

- Local integration icons and logos for Home Assistant 2026.3 and newer (#28, contributed by @frenck).
- SSDP regression tests and automated unit tests on Python 3.10 and 3.14.

## Updating

Update through HACS and restart Home Assistant. Existing configuration and entity IDs are preserved; removing and adding the integration again is not required.

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
