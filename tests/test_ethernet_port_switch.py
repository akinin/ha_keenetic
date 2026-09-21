"""Check Ethernet switch command targets without importing or contacting Home Assistant."""

import ast
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import AsyncMock, call


class CoordinatorEntityStub:
    @classmethod
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, coordinator):
        self.coordinator = coordinator


class SwitchEntityStub:
    pass


SWITCH_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "ha_keenetic"
    / "switch.py"
)
switch_tree = ast.parse(SWITCH_PATH.read_text())
ethernet_class = next(
    node
    for node in switch_tree.body
    if isinstance(node, ast.ClassDef) and node.name == "KeeneticEthernetPortSwitchEntity"
)
namespace = {
    "Any": Any,
    "CoordinatorEntity": CoordinatorEntityStub,
    "KeeneticRouterCoordinator": object,
    "SwitchEntity": SwitchEntityStub,
    "_LOGGER": logging.getLogger(__name__),
}
exec(compile(ast.Module(body=[ethernet_class], type_ignores=[]), SWITCH_PATH, "exec"), namespace)
KeeneticEthernetPortSwitchEntity = namespace["KeeneticEthernetPortSwitchEntity"]


class EthernetPortSwitchTests(unittest.IsolatedAsyncioTestCase):
    def _entity_with_admin_states(self, states, *, control_id="GigabitEthernet0/1"):
        coordinator = SimpleNamespace(
            unique_id="router",
            device_info={},
            data=SimpleNamespace(
                interface_admin_states=states,
                show_interface={"GigabitEthernet0": {"link": "down"}},
            ),
        )
        return KeeneticEthernetPortSwitchEntity(
            coordinator,
            {
                "id": "GigabitEthernet0_port_1",
                "control_id": control_id,
                "type": "port",
                "label": "Port 1",
            },
        )

    async def test_enabled_port_without_cable_is_on(self):
        entity = self._entity_with_admin_states({"GigabitEthernet0/1": True})
        self.assertIs(entity.is_on, True)

    async def test_disabled_port_is_off_even_if_link_is_up(self):
        entity = self._entity_with_admin_states({"GigabitEthernet0/1": False})
        entity.coordinator.data.show_interface["GigabitEthernet0"]["link"] = "up"
        self.assertIs(entity.is_on, False)

    async def test_missing_admin_state_is_unknown_not_inferred_from_link(self):
        entity = self._entity_with_admin_states({"GigabitEthernet0/2": True})
        self.assertIsNone(entity.is_on)

    async def test_commands_use_physical_id_without_changing_entity_id(self):
        for entity_id, control_id, port_type in (
            ("GigabitEthernet0_port_1", "GigabitEthernet0/1", "port"),
            ("GigabitEthernet1", "GigabitEthernet1/0", "wan"),
        ):
            with self.subTest(entity_id=entity_id):
                router = SimpleNamespace(turn_on_off_interface=AsyncMock())
                coordinator = SimpleNamespace(
                    unique_id="router",
                    device_info={},
                    router=router,
                    async_request_refresh=AsyncMock(),
                )
                entity = KeeneticEthernetPortSwitchEntity(
                    coordinator,
                    {
                        "id": entity_id,
                        "control_id": control_id,
                        "type": port_type,
                        "label": "Port 1",
                    },
                )

                await entity.async_turn_on()
                await entity.async_turn_off()

                self.assertEqual(entity._attr_unique_id, f"router_ethernet_port_{entity_id}")
                self.assertEqual(
                    router.turn_on_off_interface.await_args_list,
                    [call(control_id, "up"), call(control_id, "down")],
                )
                self.assertEqual(coordinator.async_request_refresh.await_count, 2)


if __name__ == "__main__":
    unittest.main()
