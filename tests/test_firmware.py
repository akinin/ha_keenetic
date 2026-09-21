"""Focused firmware polling tests without requiring a Home Assistant installation."""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock


COMPONENT = Path(__file__).resolve().parents[1] / "custom_components" / "ha_keenetic"


def load_method(filename: str, class_name: str, method_name: str, globals_: dict):
    """Compile a production method in isolation from HA-only module imports."""
    tree = ast.parse((COMPONENT / filename).read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name)
    method = next(node for node in cls.body if isinstance(node, ast.AsyncFunctionDef) and node.name == method_name)
    namespace = dict(globals_)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), filename, "exec"), namespace)
    return namespace[method_name]


class FirmwarePollingTests(unittest.IsolatedAsyncioTestCase):
    async def test_components_list_sends_explicit_empty_json(self):
        components_list = load_method("keenetic.py", "Router", "components_list", {})
        router = SimpleNamespace(api=AsyncMock(return_value={"firmware": {"version": "5.01.C.5.0-0"}}))

        await components_list(router)

        router.api.assert_awaited_once_with("post", "/rci/components/list", {})

    def coordinator_method(self):
        return load_method(
            "coordinator.py",
            "KeeneticRouterFirmwareCoordinator",
            "_async_update_data",
            {
                "COUNT_REPEATED_REQUEST_FIREWARE": 2,
                "TIMER_REPEATED_REQUEST_FIREWARE": 0,
                "FW_SANDBOX": {"stable": "main"},
                "_LOGGER": logging.getLogger(__name__),
                "asyncio": SimpleNamespace(sleep=AsyncMock()),
            },
        )

    async def test_valid_response_populates_firmware_versions(self):
        response = {
            "firmware": {"version": "5.01.C.5.0-0", "title": "5.1.5"},
            "local": {"version": "5.01.C.5.0-0", "title": "5.1.5"},
            "sandbox": "stable",
        }
        router = SimpleNamespace(
            mac="00:00:00:00:00:00",
            components_list=AsyncMock(return_value=response),
            release_notes=AsyncMock(return_value={}),
        )
        coordinator = SimpleNamespace(router=router, _version_firmware={})

        result = await self.coordinator_method()(coordinator)

        self.assertEqual(result["current"]["title"], "5.1.5")
        self.assertEqual(result["new"]["version"], "5.01.C.5.0-0")
        router.release_notes.assert_awaited_once_with("5.01.C.5.0-0", "main")

    async def test_empty_response_keeps_last_known_versions(self):
        previous = {"current": {"version": "old"}, "new": {"version": "old"}}
        router = SimpleNamespace(
            mac="00:00:00:00:00:00",
            components_list=AsyncMock(return_value={}),
            release_notes=AsyncMock(),
        )
        coordinator = SimpleNamespace(router=router, _version_firmware=previous)

        result = await self.coordinator_method()(coordinator)

        self.assertIs(result, previous)
        router.release_notes.assert_not_awaited()

    async def test_partial_response_is_not_cached(self):
        previous = {"current": {"version": "old"}, "new": {"version": "old"}}
        router = SimpleNamespace(
            mac="00:00:00:00:00:00",
            components_list=AsyncMock(return_value={"firmware": {"version": "new"}, "local": {}}),
            release_notes=AsyncMock(),
        )
        coordinator = SimpleNamespace(router=router, _version_firmware=previous)

        result = await self.coordinator_method()(coordinator)

        self.assertIs(result, previous)
        router.release_notes.assert_not_awaited()

    async def test_continued_response_is_not_cached_as_complete(self):
        previous = {"current": {"version": "old"}, "new": {"version": "old"}}
        router = SimpleNamespace(
            mac="00:00:00:00:00:00",
            components_list=AsyncMock(return_value={"continued": True}),
            release_notes=AsyncMock(),
        )
        coordinator = SimpleNamespace(router=router, _version_firmware=previous)

        result = await self.coordinator_method()(coordinator)

        self.assertIs(result, previous)
        self.assertEqual(router.components_list.await_count, 2)
        router.release_notes.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
