# v2.1.1

Bugfix release for the Keenetic Router integration.

## Fixed

- Restored compatibility of the sensor platform by avoiding newer Home Assistant constants for Wi-Fi temperature units.
- Removed the strict data-rate device class from the Wi-Fi bitrate diagnostic sensor to avoid unit validation issues on different Home Assistant versions.

## Added

- Added a Connection section to integration options.
- Router host, port, username, password, and SSL mode can now be edited after setup.
- New connection settings are validated before they are saved.

## Notes

After changing connection settings, save the options flow so Home Assistant reloads the integration with the new router data.
