# v2.1.0

Usability and diagnostics update for the Keenetic Router integration.

## What's new

- Reworked the options flow into separate sections: General, Wi-Fi, Clients, and Features/backups.
- Added a final Save action so several option sections can be changed in one flow.
- Added router diagnostics to the General options screen: model, host, mode, client count, and uptime.
- Added Wi-Fi radio diagnostic sensors for channel, channel width, bitrate, and temperature when the router provides them.
- Added USB/storage diagnostic sensors for total, free, used, used percent, and partition state.
- Expanded client `device_tracker` attributes with useful Wi-Fi/Ethernet details while keeping noisy nested data out of state attributes.

## Improved

- Updated English and Russian translations for the new options menu.
- Updated README files to describe the new settings structure and diagnostics.
- Added a clearer Wi-Fi QR security note in the options flow.

## Notes

This release is intended to be published as the latest stable release.
