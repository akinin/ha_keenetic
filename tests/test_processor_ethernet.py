"""Regression tests for the two Keenetic Ethernet port response formats."""

import importlib.util
from pathlib import Path
import unittest


PROCESSOR_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "ha_keenetic"
    / "processor_ethernet.py"
)
SPEC = importlib.util.spec_from_file_location("processor_ethernet", PROCESSOR_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
EthernetProcessor = MODULE.EthernetProcessor


class EthernetProcessorTests(unittest.IsolatedAsyncioTestCase):
    async def test_grouped_lan_ports_and_flat_wan_port(self):
        """KN-3812 has grouped switch ports and a flat WAN port object."""
        interfaces = {
            "GigabitEthernet0": {
                "port": {
                    str(number): {
                        "id": f"GigabitEthernet0/{number}",
                        "type": "Port",
                        "label": str(number),
                        "link": "up",
                        "speed": "1000",
                    }
                    for number in (1, 2, 3)
                }
            },
            "GigabitEthernet1": {
                "defaultgw": True,
                "link": "up",
                "port": {
                    "id": "GigabitEthernet1/0",
                    "index": 0,
                    "type": "Port",
                    "label": "0",
                    "link": "up",
                    "speed": "1000",
                    "duplex": "full",
                    "admin-only": False,
                },
            },
        }

        async def statistics(port_id):
            return {"rxbytes": 12, "txbytes": 34}

        result = await EthernetProcessor.process_ethernet_ports(interfaces, statistics)

        self.assertEqual(
            set(result),
            {
                "GigabitEthernet0_port_1",
                "GigabitEthernet0_port_2",
                "GigabitEthernet0_port_3",
                "GigabitEthernet1",
            },
        )
        self.assertEqual(result["GigabitEthernet1"]["type"], "wan")
        self.assertEqual(result["GigabitEthernet1"]["id"], "GigabitEthernet1")
        self.assertEqual(result["GigabitEthernet1"]["control_id"], "GigabitEthernet1/0")
        self.assertEqual(result["GigabitEthernet1"]["attributes"]["speed"], "1000")
        self.assertEqual(
            result["GigabitEthernet0_port_1"]["control_id"], "GigabitEthernet0/1"
        )
        self.assertEqual(result["GigabitEthernet0_port_1"]["attributes"]["rx_bytes"], 12)

    async def test_flat_port_without_default_gateway_is_processed(self):
        interfaces = {
            "GigabitEthernet1": {
                "port": {
                    "id": "GigabitEthernet1/0",
                    "type": "Port",
                    "label": "0",
                    "link": "up",
                    "speed": "1000",
                }
            }
        }
        requested_statistics = []

        async def statistics(port_id):
            requested_statistics.append(port_id)
            return {"rxspeed": 5}

        result = await EthernetProcessor.process_ethernet_ports(interfaces, statistics)

        port = result["GigabitEthernet1_port_GigabitEthernet1/0"]
        self.assertEqual(port["type"], "port")
        self.assertEqual(port["control_id"], "GigabitEthernet1/0")
        self.assertEqual(port["label"], "Port 0")
        self.assertEqual(port["attributes"]["rx_speed"], 5)
        self.assertEqual(requested_statistics, ["GigabitEthernet1/0"])

    async def test_malformed_port_values_do_not_discard_good_ports(self):
        interfaces = {
            "broken": "not an interface",
            "GigabitEthernet0": {
                "port": {
                    "1": {"type": "Port", "label": "1"},
                    "id": "unexpected string in port map",
                    "index": 0,
                    "misc": {"type": "Other"},
                }
            },
            "GigabitEthernet1": {"port": ["unexpected list"]},
        }

        async def statistics(port_id):
            return {}

        result = await EthernetProcessor.process_ethernet_ports(interfaces, statistics)

        self.assertEqual(set(result), {"GigabitEthernet0_port_1"})
        self.assertEqual(result["GigabitEthernet0_port_1"]["control_id"], "GigabitEthernet0/1")

    async def test_statistics_failure_does_not_discard_other_ports(self):
        interfaces = {
            "GigabitEthernet0": {
                "port": {
                    "1": {"type": "Port"},
                    "2": {"type": "Port"},
                }
            }
        }

        async def statistics(port_id):
            if port_id == "GigabitEthernet0/1":
                raise RuntimeError("statistics unavailable")
            return {"rxbytes": 42}

        result = await EthernetProcessor.process_ethernet_ports(interfaces, statistics)

        self.assertEqual(set(result), {"GigabitEthernet0_port_1", "GigabitEthernet0_port_2"})
        self.assertEqual(result["GigabitEthernet0_port_1"]["attributes"]["rx_bytes"], 0)
        self.assertEqual(result["GigabitEthernet0_port_2"]["attributes"]["rx_bytes"], 42)


if __name__ == "__main__":
    unittest.main()
