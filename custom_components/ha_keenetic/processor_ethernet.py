"""Ethernet ports processor for Keenetic integration."""
import logging
from typing import Dict, Any, Callable, Optional

_LOGGER = logging.getLogger(__name__)

class EthernetProcessor:
    """Process Ethernet ports data from Keenetic router."""

    @staticmethod
    def _control_id(interface_id: str, port_data: dict, port_id: Optional[str] = None) -> str:
        """Return the physical API interface name, never the HA entity identifier."""
        physical_id = port_data.get("id")
        if isinstance(physical_id, str) and physical_id:
            return physical_id
        if port_id is None:
            return interface_id
        port_id = str(port_id)
        if port_id.startswith(f"{interface_id}/"):
            return port_id
        return f"{interface_id}/{port_id}"

    @staticmethod
    def _iter_ports(interface_id: str, ports: Any):
        """Yield ports from both Keenetic's grouped and flat port formats."""
        if not isinstance(ports, dict):
            return

        if ports.get("type") == "Port":
            # Some routers expose a single physical port as its own object,
            # rather than as a mapping of port numbers to objects.
            yield str(ports.get("id") or interface_id), ports
            return

        for port_id, port_data in ports.items():
            if isinstance(port_data, dict) and port_data.get("type") == "Port":
                yield port_id, port_data

    @staticmethod
    async def _statistics(get_statistics_fn: Callable, port_id: str) -> dict:
        """A failed statistics request must not hide otherwise valid ports."""
        try:
            statistics = await get_statistics_fn(port_id)
        except Exception as ex:
            _LOGGER.warning("Could not read Ethernet statistics for %s: %s", port_id, ex)
            return {}
        return statistics if isinstance(statistics, dict) else {}
    
    @staticmethod
    async def process_ethernet_ports(
            interface_info: dict, 
            get_statistics_fn: Callable
        ) -> Dict[str, Any]:
        """Process Ethernet ports and return formatted data."""
        processed_ports = {}
        if not isinstance(interface_info, dict):
            _LOGGER.warning("Ignoring malformed Ethernet interface data: %s", type(interface_info).__name__)
            return {}

        wan_interface = next(
            (
                interface_id
                for interface_id, interface_data in interface_info.items()
                if isinstance(interface_data, dict) and interface_data.get("defaultgw") is True
            ),
            None,
        )

        for interface_id, interface_data in interface_info.items():
            if not isinstance(interface_data, dict):
                _LOGGER.warning("Ignoring malformed Ethernet interface %s", interface_id)
                continue

            if interface_id == wan_interface:
                interface_stats = await EthernetProcessor._statistics(get_statistics_fn, interface_id)
                port_data = interface_data.get("port")
                if not isinstance(port_data, dict):
                    port_data = {}
                processed_ports[interface_id] = {
                    "id": interface_id,
                    "control_id": EthernetProcessor._control_id(interface_id, port_data),
                    "type": "wan",
                    "description": interface_data.get("description", ""),
                    "label": "WAN",
                    "link": interface_data.get("link", "down"),
                    "attributes": {
                        "speed": port_data.get("speed", "0"),
                        "interface_name": interface_data.get("interface-name", ""),
                        "ip_address": interface_data.get("address", ""),
                        "mac": interface_data.get("mac", ""),
                        "rx_speed": interface_stats.get("rxspeed", 0),
                        "tx_speed": interface_stats.get("txspeed", 0),
                        "rx_bytes": interface_stats.get("rxbytes", 0),
                        "tx_bytes": interface_stats.get("txbytes", 0),
                    },
                }
                continue

            for port_id, port_data in EthernetProcessor._iter_ports(
                interface_id, interface_data.get("port")
            ):
                port_interface_id = f"{interface_id}_port_{port_id}"
                control_id = EthernetProcessor._control_id(interface_id, port_data, port_id)
                port_stats = await EthernetProcessor._statistics(get_statistics_fn, control_id)
                processed_ports[port_interface_id] = {
                    "id": port_interface_id,
                    "control_id": control_id,
                    "type": "port",
                    "description": port_data.get("description", ""),
                    "label": f"Port {port_data.get('label', port_id)}",
                    "link": port_data.get("link", "down"),
                    "attributes": {
                        "speed": port_data.get("speed", "0"),
                        "interface_name": port_data.get("interface-name", ""),
                        "duplex": port_data.get("duplex", ""),
                        "rx_speed": port_stats.get("rxspeed", 0),
                        "tx_speed": port_stats.get("txspeed", 0),
                        "rx_bytes": port_stats.get("rxbytes", 0),
                        "tx_bytes": port_stats.get("txbytes", 0),
                    },
                }

        _LOGGER.debug("Processed Ethernet ports: %s", processed_ports)
        return processed_ports
