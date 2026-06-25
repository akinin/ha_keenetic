# v2.0.0

Major cleanup and stabilization release based on `v2.0.0-rc2`.

## What's new

- Added binary sensors for router connectivity, interface connectivity, Ping Check, and USB/media status.
- Added number entities for Wi-Fi client idle timeout.
- Added support for more WAN/VPN interface types.
- Added selected features from `malinovsku/ha-keenetic_api`.
- Updated README files with current features, entities, options, and services.

## Fixes

- Improved handling of routers without USB/media sections.
- Improved handling of missing or unavailable Ping Check data.
- Prevented firmware coordinator crashes when the router returns a non-JSON response for firmware data.
- Fixed direct API service JSON parsing.
- Fixed deprecated Home Assistant `ScannerEntity` import.
- Fixed invalid generated sensor entity IDs for models with spaces or punctuation.
- Fixed RC interface coordinator interval units.

## Notes

This release is intended to be published as the latest stable release.
