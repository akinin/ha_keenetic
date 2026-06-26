"""Mobile modem interface processor for Keenetic integration."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
import logging

_LOGGER = logging.getLogger(__name__)

MODEM_TYPES = {
    "usbmodem",
    "usblte",
    "usbqmi",
    "yota",
    "lte",
    "lteusb",
    "cellular",
    "mobile",
}

MODEM_KEYWORDS = ("modem", "lte", "4g", "5g", "qmi", "yota", "cellular", "mobile")


class ModemProcessor:
    """Process mobile modem interfaces from Keenetic router."""

    @staticmethod
    async def process_modem_interfaces(
        interface_info: dict[str, Any],
        get_statistics_fn: Callable[[str], Any],
    ) -> dict[str, dict[str, Any]]:
        """Process 4G/5G modem interfaces and return formatted data."""
        modem_data: dict[str, dict[str, Any]] = {}

        try:
            for interface_id, interface_data in interface_info.items():
                interface_type = str(interface_data.get("type", "")).lower()
                description = str(interface_data.get("description", "")).lower()
                interface_id_lower = interface_id.lower()

                is_modem = (
                    interface_type in MODEM_TYPES
                    or any(keyword in interface_type for keyword in MODEM_KEYWORDS)
                    or any(keyword in interface_id_lower for keyword in MODEM_KEYWORDS)
                    or any(keyword in description for keyword in MODEM_KEYWORDS)
                )
                if not is_modem:
                    continue

                stats = await get_statistics_fn(interface_id)
                label = (
                    interface_data.get("description")
                    or interface_data.get("interface-name")
                    or interface_id
                )
                modem_data[interface_id] = {
                    "id": interface_id,
                    "type": "modem",
                    "description": interface_data.get("description", ""),
                    "label": label,
                    "up": interface_data.get("up", False),
                    "link": interface_data.get("link", "down"),
                    "state": interface_data.get("state", "down"),
                    "connected": interface_data.get("connected", "no"),
                    "mac": interface_data.get("mac", ""),
                    "interface-name": interface_data.get("interface-name", ""),
                    "attributes": {
                        "interface_type": interface_data.get("type", ""),
                        "description": interface_data.get("description", ""),
                        "state": interface_data.get("state", "down"),
                        "link": interface_data.get("link", "down"),
                        "connected": interface_data.get("connected", "no"),
                        "statistics": stats,
                    },
                }

                for key, value in interface_data.items():
                    if key not in modem_data[interface_id]:
                        modem_data[interface_id][key] = value
                    modem_data[interface_id]["attributes"].setdefault(key, value)

            _LOGGER.debug("Processed modem interfaces: %s", list(modem_data))
            return modem_data
        except Exception as ex:
            _LOGGER.error("Error processing modem interfaces: %s", ex)
            return {}
