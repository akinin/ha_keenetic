"""SSDP and manual config-flow regressions without a Home Assistant install."""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock
from urllib.parse import urlparse


CONFIG_FLOW = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "ha_keenetic"
    / "config_flow.py"
)
CONF_HOST = "host"
CONF_PASSWORD = "password"
CONF_PORT = "port"
CONF_ROUTER_SERIAL = "router_serial"
CONF_SSL = "ssl"
CONF_USERNAME = "username"


class _VoluptuousStub:
    """Keep form construction observable without importing voluptuous."""

    @staticmethod
    def Required(key: str, default: object = None) -> str:
        return key

    @staticmethod
    def Schema(fields: dict) -> dict:
        return fields


def _load_flow_code() -> dict:
    """Run production helpers and methods with only their HA boundaries stubbed."""
    tree = ast.parse(CONFIG_FLOW.read_text(encoding="utf-8"))
    helpers = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {
            "_host_from_address",
            "_matches_authenticated_router",
            "_same_serial",
            "_update_discovered_host",
        }
    ]
    config_flow = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "ConfigFlow"
    )
    methods = [
        node
        for node in config_flow.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name in {"async_step_ssdp", "async_step_user"}
    ]
    namespace = {
        "urlparse": urlparse,
        "vol": _VoluptuousStub,
        "cv": SimpleNamespace(string=str),
        "config_entries": SimpleNamespace(SOURCE_SSDP="ssdp"),
        "format_mac": lambda address: address,
        "get_api": AsyncMock(),
        "_LOGGER": logging.getLogger(__name__),
        "STEP_USER_DATA_SCHEMA": {},
        "CONF_HOST": CONF_HOST,
        "CONF_PASSWORD": CONF_PASSWORD,
        "CONF_PORT": CONF_PORT,
        "CONF_ROUTER_SERIAL": CONF_ROUTER_SERIAL,
        "CONF_SSL": CONF_SSL,
        "CONF_USERNAME": CONF_USERNAME,
        "FlowResult": dict,
        "SsdpServiceInfo": object,
    }
    extracted = ast.Module(body=helpers + methods, type_ignores=[])
    exec(compile(ast.fix_missing_locations(extracted), str(CONFIG_FLOW), "exec"), namespace)
    return namespace


class _FakeFlow:
    def __init__(self, entries: list[SimpleNamespace] | None = None, source: str = "ssdp"):
        self.entries = entries or []
        self.source = source
        self.unique_id = None
        self.hass = SimpleNamespace(
            config_entries=SimpleNamespace(async_update_entry=Mock())
        )
        self.handle_without_id = AsyncMock()

    async def async_set_unique_id(self, unique_id: str) -> None:
        self.unique_id = unique_id

    def _abort_if_unique_id_configured(self) -> None:
        # The tests below use an existing legacy ID, not an identical SSDP ID.
        assert all(entry.unique_id != self.unique_id for entry in self.entries)

    def _async_current_entries(self) -> list[SimpleNamespace]:
        return self.entries

    async def _async_handle_discovery_without_unique_id(self) -> None:
        await self.handle_without_id()

    @staticmethod
    def async_abort(*, reason: str) -> dict:
        return {"type": "abort", "reason": reason}

    @staticmethod
    def async_show_form(*, step_id: str, data_schema: dict, **kwargs) -> dict:
        return {"type": "form", "step_id": step_id, "data_schema": data_schema, **kwargs}

    @staticmethod
    def async_create_entry(*, title: str, data: dict) -> dict:
        return {"type": "create_entry", "title": title, "data": data}


def _discovery(host: str = "192.0.2.20", serial: str = "SERIAL-123"):
    return SimpleNamespace(
        ssdp_location=f"http://{host}:80/description.xml",
        upnp={
            "manufacturer": "Keenetic",
            "serialNumber": serial,
            "friendlyName": "Keenetic Test",
        },
    )


def _router(serial: str = "SERIAL-123"):
    return SimpleNamespace(
        mac="aa:bb:cc:dd:ee:ff",
        serial_number=serial,
        show_version=AsyncMock(
            return_value={"vendor": "Keenetic", "model": "Test", "device": "Router"}
        ),
    )


def _user_data(host: str = "http://192.0.2.20") -> dict:
    return {
        CONF_USERNAME: "admin",
        CONF_PASSWORD: "password",
        CONF_HOST: host,
        CONF_PORT: 80,
        CONF_SSL: False,
    }


class DiscoveryFlowTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.code = _load_flow_code()
        self.code["get_api"].return_value = _router()

    async def test_new_ssdp_flow_preserves_discovery_unique_id_after_credentials(self):
        flow = _FakeFlow()

        form = await self.code["async_step_ssdp"](flow, _discovery())
        created = await self.code["async_step_user"](flow, _user_data())

        self.assertEqual(form["type"], "form")
        self.assertEqual(form["step_id"], "user")
        self.assertEqual(flow.unique_id, "SERIAL-123")
        self.assertEqual(created["type"], "create_entry")
        self.assertEqual(
            created["data"], {**_user_data(), CONF_ROUTER_SERIAL: "SERIAL-123"}
        )
        flow.hass.config_entries.async_update_entry.assert_not_called()

    async def test_legacy_entry_at_same_host_aborts_before_credentials(self):
        existing = SimpleNamespace(
            unique_id="Keenetic Router aabbccddeeff",
            data=_user_data("http://192.0.2.20"),
        )
        flow = _FakeFlow(entries=[existing])

        result = await self.code["async_step_ssdp"](flow, _discovery())

        self.assertEqual(result, {"type": "abort", "reason": "already_configured"})
        self.assertEqual(flow.unique_id, "SERIAL-123")
        self.code["get_api"].assert_not_awaited()
        flow.hass.config_entries.async_update_entry.assert_not_called()

    async def test_authenticated_legacy_entry_at_new_host_updates_without_duplicate(self):
        old_data = _user_data("http://192.0.2.10")
        existing = SimpleNamespace(
            unique_id="Keenetic Router aabbccddeeff", data=old_data
        )
        flow = _FakeFlow(entries=[existing])
        new_data = _user_data("http://192.0.2.20")

        form = await self.code["async_step_ssdp"](flow, _discovery())
        result = await self.code["async_step_user"](flow, new_data)

        self.assertEqual(form["type"], "form")
        self.assertEqual(result, {"type": "abort", "reason": "already_configured"})
        self.assertEqual(existing.unique_id, "Keenetic Router aabbccddeeff")
        flow.hass.config_entries.async_update_entry.assert_called_once_with(
            existing, data={**new_data, CONF_ROUTER_SERIAL: "SERIAL-123"}
        )

    async def test_stored_serial_updates_https_host_without_duplicate(self):
        old_data = {
            **_user_data("https://192.0.2.10"),
            CONF_PORT: 443,
            CONF_SSL: True,
            CONF_ROUTER_SERIAL: "serial-123",
        }
        existing = SimpleNamespace(
            unique_id="Keenetic Router aabbccddeeff",
            data=old_data,
        )
        flow = _FakeFlow(entries=[existing])

        result = await self.code["async_step_ssdp"](flow, _discovery())

        self.assertEqual(result, {"type": "abort", "reason": "already_configured"})
        self.assertEqual(flow.unique_id, "SERIAL-123")
        self.assertEqual(existing.unique_id, "Keenetic Router aabbccddeeff")
        flow.hass.config_entries.async_update_entry.assert_called_once_with(
            existing,
            data={**old_data, CONF_HOST: "https://192.0.2.20"},
        )

    async def test_stored_serial_at_same_host_does_not_update(self):
        existing = SimpleNamespace(
            unique_id="Keenetic Router aabbccddeeff",
            data={
                **_user_data("https://192.0.2.20"),
                CONF_PORT: 443,
                CONF_SSL: True,
                CONF_ROUTER_SERIAL: "serial-123",
            },
        )
        flow = _FakeFlow(entries=[existing])

        result = await self.code["async_step_ssdp"](flow, _discovery())

        self.assertEqual(result, {"type": "abort", "reason": "already_configured"})
        flow.hass.config_entries.async_update_entry.assert_not_called()

    async def test_udn_without_serial_aborts_at_existing_host(self):
        """An existing entry still matches by host if SSDP omits its serial."""
        existing = SimpleNamespace(
            unique_id="Keenetic Router aabbccddeeff",
            data={**_user_data(), CONF_ROUTER_SERIAL: "SERIAL-123"},
        )
        flow = _FakeFlow(entries=[existing])
        discovery = _discovery(serial="")
        discovery.upnp["UDN"] = "uuid:router-123"

        result = await self.code["async_step_ssdp"](flow, discovery)

        self.assertEqual(result, {"type": "abort", "reason": "already_configured"})
        self.assertEqual(flow.unique_id, "uuid:router-123")
        flow.hass.config_entries.async_update_entry.assert_not_called()

    async def test_changed_host_cannot_claim_discovered_routers_id(self):
        """An edited SSDP form must not bind another router to the SSDP ID."""
        self.code["get_api"].return_value = _router(serial="OTHER-ROUTER")
        flow = _FakeFlow()

        await self.code["async_step_ssdp"](flow, _discovery())
        result = await self.code["async_step_user"](
            flow, _user_data("http://192.0.2.99")
        )

        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "user")
        self.assertEqual(result["errors"], {"base": "cannot_connect"})
        self.assertEqual(flow.unique_id, "SERIAL-123")
        flow.hass.config_entries.async_update_entry.assert_not_called()

    async def test_changed_host_preserves_embedded_port_and_path(self):
        old_data = {
            **_user_data("https://192.0.2.10:8443/router"),
            CONF_PORT: 8443,
            CONF_SSL: True,
            CONF_ROUTER_SERIAL: "serial-123",
        }
        existing = SimpleNamespace(
            unique_id="Keenetic Router aabbccddeeff", data=old_data
        )
        flow = _FakeFlow(entries=[existing])

        result = await self.code["async_step_ssdp"](flow, _discovery())

        self.assertEqual(result, {"type": "abort", "reason": "already_configured"})
        flow.hass.config_entries.async_update_entry.assert_called_once_with(
            existing,
            data={**old_data, CONF_HOST: "https://192.0.2.20:8443/router"},
        )

    async def test_ssdp_id_updates_https_host_without_changing_id(self):
        old_data = {
            **_user_data("https://192.0.2.10"),
            CONF_PORT: 443,
            CONF_SSL: True,
        }
        existing = SimpleNamespace(unique_id="SERIAL-123", data=old_data)
        flow = _FakeFlow(entries=[existing])

        result = await self.code["async_step_ssdp"](flow, _discovery())

        self.assertEqual(result, {"type": "abort", "reason": "already_configured"})
        self.assertEqual(existing.unique_id, "SERIAL-123")
        flow.hass.config_entries.async_update_entry.assert_called_once_with(
            existing,
            data={**old_data, CONF_HOST: "https://192.0.2.20"},
        )

    async def test_manual_duplicate_aborts_without_changing_existing_entry(self):
        old_data = _user_data("http://192.0.2.10")
        existing = SimpleNamespace(
            unique_id="Keenetic Router aabbccddeeff", data=old_data
        )
        flow = _FakeFlow(entries=[existing], source="user")

        result = await self.code["async_step_user"](
            flow, _user_data("http://192.0.2.20")
        )

        self.assertEqual(result, {"type": "abort", "reason": "already_configured"})
        self.assertEqual(existing.data, old_data)
        flow.hass.config_entries.async_update_entry.assert_not_called()
