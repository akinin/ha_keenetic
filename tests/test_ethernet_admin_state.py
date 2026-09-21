"""Unit tests for read-only Keenetic Ethernet administrative state collection."""

import ast
import logging
from pathlib import Path
import unittest
from unittest.mock import AsyncMock


KEENETIC_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "ha_keenetic"
    / "keenetic.py"
)
tree = ast.parse(KEENETIC_PATH.read_text())
router_class = next(
    node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Router"
)
admin_method = next(
    node
    for node in router_class.body
    if isinstance(node, ast.AsyncFunctionDef)
    and node.name == "get_interface_admin_states"
)
namespace = {"_LOGGER": logging.getLogger(__name__)}
exec(compile(ast.Module(body=[admin_method], type_ignores=[]), KEENETIC_PATH, "exec"), namespace)
get_interface_admin_states = namespace["get_interface_admin_states"]


class EthernetAdminStateTests(unittest.IsolatedAsyncioTestCase):
    async def test_reads_config_once_and_keeps_only_boolean_enablement(self):
        router = type("FakeRouter", (), {})()
        router.api = AsyncMock(
            return_value={
                "GigabitEthernet0/0": {"up": True, "password": "not-retained"},
                "GigabitEthernet0/1": {"up": False},
                "GigabitEthernet0/2": {"link": "down"},
                "GigabitEthernet0/3": {"up": "false"},
                "broken": None,
            }
        )

        result = await get_interface_admin_states(router)

        self.assertEqual(
            result,
            {"GigabitEthernet0/0": True, "GigabitEthernet0/1": False},
        )
        router.api.assert_awaited_once_with("get", "/rci/interface")

    async def test_bad_or_failed_read_returns_unknown_states(self):
        router = type("FakeRouter", (), {})()
        router.api = AsyncMock(return_value=[])
        self.assertEqual(await get_interface_admin_states(router), {})

        router.api = AsyncMock(side_effect=RuntimeError("offline"))
        self.assertEqual(await get_interface_admin_states(router), {})


if __name__ == "__main__":
    unittest.main()
