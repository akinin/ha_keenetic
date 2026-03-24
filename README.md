[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/Sessim/ha_keenetic_sms?style=flat&color=%23A349A4)](https://github.com/Sessim/ha_keenetic_sms)
# Keenetic Router Integration for Home Assistant
[Russian ver.](README_RU.md)

This is a Home Assistant custom integration for Keenetic Routers. It provides detailed information about your Keenetic router including WiFi networks, ethernet ports, and mesh network status.

## Features

- Monitor router system information (CPU, memory, uptime)
- Control WiFi networks (enable/disable)
- View ethernet port status and statistics
- Monitor mesh network nodes
- View detailed interface statistics
- Send and read SMS through Keenetic USB/LTE modem interfaces

## Installation

### HACS (Recommended)

1. Open HACS
2. Click on "Integrations"
3. Click the "+" button
4. Search for "Keenetic Router"
5. Click "Install"
6. Restart Home Assistant

### Manual Installation

1. Download the latest release
2. Copy the `ha_keenetic_sms` folder to your `custom_components` directory
3. Restart Home Assistant

### Important Points

The integration communicates with the router via REST API, for which you need to configure port forwarding:

1. Access your router's web interface
2. Go to "Port Forwarding" > "Add rule"
3. Configure the following parameters:
   - Enable rule: ✓ (enabled)
   - Description: rest api
   - Input: Other destination
   - IP address: 192.168.1.0 (local network address where HomeAssistant is located)
   - Subnet mask: 255.255.255.0 (/24)
   - Output: This Keenetic device
   - Protocol: TCP
   - Rule type: Single port
   - Open the port: 81
   - Redirect to port: 79
   - Work schedule: Always on

![Rest API](images/0.png)

⚠️ Security Recommendation:
For enhanced security, it is recommended to configure Firewall rules to allow REST API access only from your Home Assistant IP address. This helps protect the router from unauthorized access within the local network.

To enable automatic router discovery, you need to enable UPnP on your Keenetic:

1. Access your router's web interface
2. Go to "System Settings" > "Component options"
3. Make sure "UPnP" is enabled:

![UPnP setting](images/0-1.png)

## Automatic Setup

If UPnP is enabled, the integration will discover the router.

![Discovered integration](images/1.png)

## Manual Setup

1. Go to "Settings" > "Devices & services"
2. Click the "+ ADD INTEGRATION" button
3. Search for "Keenetic Router"
4. Enter your router details:
   - IP address (default: 192.168.1.1)
   - Port (default: 81)
   - Username (default: admin)
   - Password

![Integration search](images/1-1.png)

![Connection form](images/2.png)

![Successful connection](images/3.png)

## Supported Devices

The integration has been tested with the following models:
- Keenetic Giga
- Keenetic Hero 4g
- Keenetic Sprinter SE

Other Keenetic models should also work.

## Available Entities

### Sensors
- System information (CPU, memory, uptime)
- WiFi networks status
- Ethernet ports status
- Mesh network nodes status
- SMS counters for modem interfaces with latest-message attributes

### Services
- `ha_keenetic_sms.read_sms` - read modem SMS list for an interface
- `ha_keenetic_sms.read_sms_item` - read a modem SMS by ID
- `ha_keenetic_sms.send_sms` - send SMS through a modem
- `ha_keenetic_sms.delete_sms` - delete a modem SMS by ID

### Switches
- WiFi networks (enable/disable)

![Sensors](images/4.png)

![Diagnostics](images/5.png)

![WiFi interfaces control](images/7.png)

![WiFi interface control](images/7-1.png)

![WAN information](images/8.png)

Mesh devices information (if available):

![Mesh information](images/9.png)

## Contributing

Any suggestions for improvement are welcome.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
