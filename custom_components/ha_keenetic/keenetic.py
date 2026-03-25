"""The Keenetic API."""

from __future__ import annotations
from hashlib import md5, sha256
from collections.abc import Mapping
from typing import Literal, Any
import asyncio
import aiohttp
import asyncssh
import logging
import aiofiles.os
import re
import shlex
from pathlib import Path
from dataclasses import dataclass
from urllib.parse import urlsplit

_LOGGER = logging.getLogger(__name__)

@dataclass
class KeeneticFullData:
    show_system: dict[str, Any]
    show_ip_hotspot: DataDevice
    show_interface: dict[str, Any]
    show_rc_ip_static: dict[str, Any]
    show_associations: dict[str, Any]
    show_ip_hotspot_policy: dict[str, Any]
    priority_interface: dict[str, Any]
    show_rc_ip_http: dict[str, Any]
    show_rc_system_usb: dict[str, Any]
    show_media: dict[str, Any]
    stat_interface: dict[str, Any]
    show_modem_sms: dict[str, list[dict[str, Any]]]

@dataclass
class DataDevice():
    mac: str
    name: str
    hostname: str
    ip: str
    active: bool
    interface_id: str
    uptime: int
    rssi: str
    rxbytes: int
    txbytes: int

@dataclass
class DataPortForwarding():
    name: str
    interface: str
    protocol: str
    port: int
    end_port: str
    to_host: str
    index: str
    comment: str
    disable: bool = False

@dataclass
class DataRcInterface():
    id: str
    name_interface: str
    interface: str
    ssid: str
    password: str
    active: str
    rename: str
    description: str


INTERFACES_WIFI_NAME = {
    "WifiMaster0": "WiFi %s 2.4G",
    "WifiMaster1": "WiFi %s 5G"
}

LIST_INTERFACES = [
    "UsbModem",
    "UsbQmi",
    "Davicom",
    "UsbLte",
    "Yota",
    "PPPoE",
    "SSTP",
    "PPTP",
    "L2TP",
    "Wireguard",
    "OpenVPN",
    "EoIP",
    "GigabitEthernet",
    "Ethernet",
]

MODEM_INTERFACES = {
    "UsbModem",
    "UsbQmi",
    "UsbLte",
    "Yota",
}

class Router:
    def __init__(
        self, 
        session: aiohttp.ClientSession, 
        username="admin", 
        password="admin", 
        host="192.168.1.1", 
        port: int = 80, 
        ssl: bool | None = False,
        ):
        self._session = session
        self.host = host
        self.url_router = f'{host}:{port}'
        self._username = username
        self._password = password
        self.request_interface = {}
        self._ssh_lock = asyncio.Lock()
        self._ssh_port = 22
        self._ssh_host = self._normalize_ssh_host(host)
        self._sms_enabled = False
        self._sms_interface = ""

        self._mac = ""
        self._serial_number = ""
        self._model = ""
        self._hw_type = ""
        self._hw_id = ""
        self._name_device = ""
        self._fw_branch = None

    @property
    def mac(self):
        return self._mac
    @property
    def serial_number(self):
        return self._serial_number
    @property
    def model(self):
        return self._model
    @property
    def hw_type(self):
        return self._hw_type
    @property
    def hw_id(self):
        return self._hw_id
    @property
    def fw_version(self):
        return self._fw_version
    @property
    def hw_version(self):
        return self._hw_version
    @property
    def name_device(self):
        return self._name_device
    @property
    def fw_branch(self):
        return self._fw_branch or "unknown"
    @property
    def hostname(self):
        return self._hostname
    @property
    def domainname(self):
        return self._domainname

    def _normalize_ssh_host(self, host: str) -> str:
        if "://" in host:
            parsed = urlsplit(host)
            if parsed.hostname:
                return parsed.hostname
        return host.split("/")[0]

    async def _run_ssh_command(self, command: str) -> str:
        async with self._ssh_lock:
            _LOGGER.debug("%s ssh sms command - %s", self._mac, command)
            async with asyncssh.connect(
                self._ssh_host,
                port=self._ssh_port,
                username=self._username,
                password=self._password,
                known_hosts=None,
                client_keys=None,
            ) as conn:
                result = await conn.run(command, check=False)

            stdout = (result.stdout or "").strip()
            stderr = (result.stderr or "").strip()
            output = stdout or stderr

            if result.exit_status not in (0, None) and not output:
                raise Exception(
                    f"SSH command failed with exit status {result.exit_status}: {command}"
                )

            if not output and result.exit_status not in (0, None):
                raise Exception(stderr or f"SSH command failed: {command}")

            return output

    def configure_sms(
        self,
        enabled: bool = False,
        interface: str = "",
        ssh_port: int = 22,
    ) -> None:
        self._sms_enabled = enabled
        self._sms_interface = interface.strip()
        self._ssh_port = ssh_port

    def get_default_sms_interface(self) -> str:
        return self._sms_interface

    def _quote_sms_cli_arg(self, value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'


    async def async_setup_obj(self):
        await self.auth()

        data_show_identification = await self.show_identification()
        self._mac = data_show_identification["mac"]
        self._serial_number = data_show_identification["serial"]

        data_show_version = await self.show_version()
        self._model = data_show_version["model"]
        self._hw_id = data_show_version["hw_id"]
        self._fw_version = data_show_version.get("title", "")
        self._hw_version = data_show_version.get("hw_version", "")
        self._name_device = data_show_version["device"]

        data_show_system = await self.show_system()
        self._hostname = data_show_system.get("hostname", "")
        self._domainname = data_show_system.get("domainname", "")

        data_show_system_mode = await self.show_system_mode()
        self._hw_type = data_show_system_mode["active"]

        if self._hw_type == "router":
            # data_show_rc_interface_ip_global = await self.show_rc_interface_ip_global()
            data_show_interface = await self.show_interface()
            for interface, data_interface in data_show_interface.items():
                if (
                    (
                        data_interface.get('type', 'No') in LIST_INTERFACES
                        and data_interface.get('security-level', False) == 'public'
                    )
                    or data_interface.get('global', False)
                    ):
                    self.request_interface[interface] = f"{data_interface['type']} {data_interface.get('description', '')}"
        _LOGGER.debug(f'{self._mac} request_interface - {self.request_interface}')
        return True

    async def get_ethernet_ports(self):
        """Get information about ethernet ports."""
        try:
            interfaces = await self.show_interface()

            async def get_port_statistics(port_id):
                try:
                    stats = await self.show_interface_stat(port_id)
                    return stats
                except Exception as ex:
                    _LOGGER.error(f"Error getting statistics for port {port_id}: {ex}")
                    return {}

            from .processor_ethernet import EthernetProcessor
            return await EthernetProcessor.process_ethernet_ports(interfaces, get_port_statistics)
        except Exception as ex:
            _LOGGER.error(f"Error processing ethernet ports: {ex}")
            return {}

    async def get_mesh_nodes(self):
        try:
            mesh_info = await self.api("get", "/rci/show/mws/member")

            _LOGGER.debug("Mesh network information from /rci/show/mws/member: %s", mesh_info)

            from .processor_mesh import MeshProcessor
            return MeshProcessor.process_mesh_nodes(mesh_info)
        except Exception as ex:
            _LOGGER.error(f"Error processing mesh nodes: {ex}")
            return {}

    async def get_vpn_interfaces(self):
        try:
            interfaces = await self.show_interface()

            _LOGGER.debug("Available interfaces for VPN processing: %s", list(interfaces.keys()))

            for interface_id, interface_data in interfaces.items():
                if 'wireguard' in interface_id.lower() or 'wg' in interface_id.lower():
                    _LOGGER.debug("Found potential WireGuard interface: %s, data: %s", interface_id, interface_data)

            async def get_interface_statistics(interface_id):
                try:
                    stats = await self.show_interface_stat(interface_id)
                    return stats
                except Exception as ex:
                    _LOGGER.error(f"Error getting statistics for interface {interface_id}: {ex}")
                    return {}

            from .processor_vpn import VpnProcessor
            vpn_interfaces = await VpnProcessor.process_vpn_interfaces(interfaces, get_interface_statistics)

            _LOGGER.debug("Found VPN interfaces: %s", list(vpn_interfaces.keys()))
            
            return vpn_interfaces
        except Exception as ex:
            _LOGGER.error(f"Error processing VPN interfaces: {ex}")
            return {}

    async def async_download_file(self, download_url, folder):
        try:
            await aiofiles.os.makedirs(folder, exist_ok=True)
            async with self._session.get(download_url, timeout=180) as response:
                    if response.status != 200:
                        raise Exception('Got non-200 response!')
                    async with aiofiles.open(f"{folder}/{self._mac.replace(':', '')}-{response.content_disposition.filename}", 'wb') as file:
                        async for data, _ in response.content.iter_chunks():
                            await file.write(data)
        except asyncio.TimeoutError as err:
            raise Exception("TimeoutError") from err
        return True

    async def reguest_api(self, method: str, endpoint: str, json: Mapping[str, Any] | None = None, headers: str | None = None) -> tuple[aiohttp.ClientResponse]:
        url = self.url_router + endpoint
        try:
            _LOGGER.debug(f'{self._mac} request - {endpoint} - {json}')
            async with self._session.request(method=method, url=url, json=json, headers=headers) as res:
                if res.status == 200 and res.content_type == 'application/json':
                    result = await res.json()
                elif res.status == 200 and res.content_type == 'application/javascript':
                    result = await res.text()
                    result = self.data_parser(result)
                elif res.status == 200 and res.content_type.startswith("text/"):
                    result = await res.text()
                else:
                    result = res
                _LOGGER.debug(f'{self._mac} status - {endpoint} {res.status}')
        except asyncio.TimeoutError as err:
            raise Exception("TimeoutError") from err
        return result

    async def get_wifi_interfaces(self):
        try:
            interfaces = await self.show_interface()
            rc_interfaces = await self.show_rc_interface()

            async def get_associations():
                try:
                    associations = await self.show_associations()
                    _LOGGER.debug(f"Associations type: {type(associations)}, data: {associations}")
                    return associations
                except Exception as ex:
                    _LOGGER.error(f"Error getting associations: {ex}")
                    return {}

            from .processor_wifi import WiFiProcessor
            return await WiFiProcessor.process_wifi_interfaces(interfaces, rc_interfaces, get_associations)
        except Exception as ex:
            _LOGGER.error(f"Error processing WiFi interfaces: {ex}")
            return {}

    async def get_usb_ports(self):
        try:
            usb_info = []
            
            if hasattr(self, 'data') and hasattr(self.data, 'show_rc_system_usb'):
                usb_info = self.data.show_rc_system_usb
                _LOGGER.debug(f"Using existing USB info from show_rc_system_usb: {usb_info}")

            if not usb_info:
                try:
                    _LOGGER.debug("Trying to get USB info directly")
                    response = await self.api("get", "/rci/show/rc/system")
                    
                    if isinstance(response, dict) and "usb" in response:
                        usb_info = response.get("usb", [])
                    elif isinstance(response, dict) and "rc" in response and "system" in response.get("rc", {}) and "usb" in response.get("rc", {}).get("system", {}):
                        usb_info = response.get("rc", {}).get("system", {}).get("usb", [])
                    elif isinstance(response, dict) and "show" in response and "rc" in response.get("show", {}) and "system" in response.get("show", {}).get("rc", {}) and "usb" in response.get("show", {}).get("rc", {}).get("system", {}):
                        usb_info = response.get("show", {}).get("rc", {}).get("system", {}).get("usb", [])
                    
                    _LOGGER.debug(f"Got USB info directly: {usb_info}")
                except Exception as ex:
                    _LOGGER.error(f"Error getting USB info directly: {ex}")

            if isinstance(usb_info, dict):
                usb_info = [usb_info]
            elif not isinstance(usb_info, list):
                usb_info = []

            async def get_media_info(media_name):
                try:
                    if hasattr(self, 'data') and hasattr(self.data, 'show_media'):
                        media_info = self.data.show_media.get(media_name)
                        return media_info
                    return None
                except Exception as ex:
                    _LOGGER.error(f"Error getting media info for {media_name}: {ex}")
                    return None

            from .processor_usb import UsbProcessor
            return await UsbProcessor.process_usb_ports(usb_info, get_media_info)
        except Exception as ex:
            _LOGGER.error(f"Error processing USB ports: {ex}", exc_info=True)
            return {}

    def get_modem_interface_ids(self, interfaces: Mapping[str, Any] | None = None) -> list[str]:
        interfaces = interfaces or {}
        modem_interfaces = []
        for interface_id, interface_data in interfaces.items():
            interface_type = interface_data.get("type")
            if interface_type in MODEM_INTERFACES:
                modem_interfaces.append(interface_id)
        return modem_interfaces

    def _extract_sms_payload(self, response: Any) -> list[dict[str, Any]]:
        if isinstance(response, list):
            return [item for item in response if isinstance(item, dict)]

        if not isinstance(response, dict):
            return []

        for key in ("sms", "messages", "message", "items", "inbox", "outbox"):
            value = response.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict):
                nested = self._extract_sms_payload(value)
                if nested:
                    return nested

        for value in response.values():
            if isinstance(value, dict):
                nested = self._extract_sms_payload(value)
                if nested:
                    return nested
            elif isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
                sample_keys = set().union(*(item.keys() for item in value[:3]))
                if sample_keys.intersection({"text", "body", "message", "phone", "sender", "number"}):
                    return value

        return []

    def _parse_cli_sms_output(self, response: str) -> dict[str, Any]:
        stats: dict[str, Any] = {}
        messages: list[dict[str, Any]] = []
        current_message: dict[str, Any] | None = None
        current_field: str | None = None

        for raw_line in response.splitlines():
            line = raw_line.rstrip()
            stripped = line.strip()
            if not stripped or stripped.startswith("(config)>"):
                continue

            msg_match = re.match(r"messages,\s*id\s*=\s*(.+?):$", stripped, re.IGNORECASE)
            if msg_match:
                current_message = {"id": msg_match.group(1).strip()}
                messages.append(current_message)
                current_field = None
                continue

            key, sep, value = stripped.partition(":")
            if sep:
                normalized_key = key.strip().lower().replace(" ", "-")
                normalized_value = value.strip()
                if current_message is None:
                    stats[normalized_key] = normalized_value
                else:
                    current_message[normalized_key] = normalized_value
                current_field = normalized_key
                continue

            if current_message is not None and current_field:
                existing_value = current_message.get(current_field, "")
                current_message[current_field] = f"{existing_value}\n{stripped}".strip()

        if messages:
            return {"messages": messages, "stats": stats}

        if stats:
            return {"messages": [stats], "stats": {}}

        return {"messages": [], "stats": {}}

    def _clean_sms_text(self, value: str) -> str:
        # Keenetic CLI may append ANSI/terminal cleanup sequences to wrapped SMS text.
        cleaned = value.replace("\\e[K", "").replace("\x1b[K", "")
        cleaned = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", cleaned)
        return cleaned.strip()

    def _normalize_sms_message(self, message: dict[str, Any], default_id: int | str) -> dict[str, Any]:
        sender = (
            message.get("from")
            or message.get("sender")
            or message.get("phone")
            or message.get("number")
            or message.get("address")
            or ""
        )
        text = (
            message.get("text")
            or message.get("body")
            or message.get("message")
            or message.get("content")
            or ""
        )
        text = self._clean_sms_text(text)
        timestamp = (
            message.get("date")
            or message.get("datetime")
            or message.get("time")
            or message.get("received")
            or message.get("timestamp")
            or ""
        )
        return {
            "id": message.get("id") or message.get("index") or default_id,
            "sender": sender,
            "recipient": message.get("to") or message.get("recipient") or "",
            "text": text,
            "status": message.get("status") or message.get("state") or "",
            "timestamp": timestamp,
            "parts": message.get("parts"),
            "total_parts": message.get("total-parts") or message.get("total_parts"),
            "is_read": message.get("read"),
            "raw": message,
        }

    def _normalize_sms_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized_messages = []
        for index, message in enumerate(messages):
            normalized_messages.append(self._normalize_sms_message(message, index))
        return normalized_messages

    def _normalize_sms_response(self, response: Any) -> dict[str, Any]:
        if isinstance(response, str):
            parsed = self._parse_cli_sms_output(response)
            return {
                "messages": self._normalize_sms_messages(parsed["messages"]),
                "stats": parsed["stats"],
                "raw": response,
            }

        messages = self._extract_sms_payload(response)
        return {
            "messages": self._normalize_sms_messages(messages),
            "stats": {},
            "raw": response,
        }

    async def get_modem_sms_details(self, interface: str, folder: str = "inbox") -> dict[str, Any]:
        response = await self._run_ssh_command(f"sms {shlex.quote(interface)} list")
        normalized = self._normalize_sms_response(response)
        normalized["transport"] = "ssh"
        normalized["command"] = f"sms {interface} list"
        normalized["folder"] = folder
        return normalized

    async def get_modem_sms(self, interface: str, folder: str = "inbox") -> list[dict[str, Any]]:
        details = await self.get_modem_sms_details(interface, folder)
        return details["messages"]

    async def _call_sms_action(
        self,
        interface: str,
        action: str,
        payload: Mapping[str, Any] | None = None,
    ) -> Any:
        payload = payload or {}
        endpoints = [
            f"/rci/sms/{interface}/{action}",
            f"/rci/interface/{interface}/sms/{action}",
            f"/rci/interface/{interface}/modem/{action}",
            f"/rci/interface/{interface}/messages/{action}",
            f"/rci/interface/{interface}/modem/sms/{action}",
            f"/rci/interface/{interface}/modem/messages/{action}",
        ]

        last_error = None
        for endpoint in endpoints:
            try:
                response = await self.api("post", endpoint, payload)
                if isinstance(response, dict):
                    return response
                if isinstance(response, list):
                    return response
                if isinstance(response, str):
                    response_text = response.strip()
                    if response_text:
                        return {"status": "success", "endpoint": endpoint, "details": response_text}
                if hasattr(response, "status") and response.status == 200:
                    return {"status": "success", "endpoint": endpoint}
            except Exception as ex:
                last_error = ex
                _LOGGER.debug("SMS action endpoint %s is unavailable for %s: %s", endpoint, interface, ex)

        if last_error is not None:
            raise last_error
        raise Exception(f"SMS action {action} is not supported for interface {interface}")

    async def send_modem_sms(self, interface: str, phone: str, text: str) -> Any:
        command = (
            f"sms {shlex.quote(interface)} send "
            f"{self._quote_sms_cli_arg(phone)} {self._quote_sms_cli_arg(text)}"
        )
        response = await self._run_ssh_command(command)
        return {
            "status": "success",
            "transport": "ssh",
            "command": f"sms {interface} send {phone} <text>",
            "details": response,
        }

    async def read_modem_sms(self, interface: str, sms_id: str) -> Any:
        command = f"sms {shlex.quote(interface)} read {shlex.quote(sms_id)}"
        response = await self._run_ssh_command(command)
        normalized = self._normalize_sms_response(response)
        if normalized["messages"]:
            return normalized["messages"][0]
        return {
            "transport": "ssh",
            "command": f"sms {interface} read {sms_id}",
            "details": response,
        }

    async def delete_modem_sms(self, interface: str, sms_id: str) -> Any:
        command = f"sms {shlex.quote(interface)} delete {shlex.quote(sms_id)}"
        response = await self._run_ssh_command(command)
        return {
            "status": "success",
            "transport": "ssh",
            "command": f"sms {interface} delete {sms_id}",
            "details": response,
        }

    async def get_all_modem_sms(self, interfaces: Mapping[str, Any] | None = None) -> dict[str, list[dict[str, Any]]]:
        if not self._sms_enabled:
            return {}

        if self._sms_interface:
            return {self._sms_interface: await self.get_modem_sms(self._sms_interface)}

        interfaces = interfaces or await self.show_interface()
        modem_interfaces = self.get_modem_interface_ids(interfaces)
        modem_sms: dict[str, list[dict[str, Any]]] = {}

        for interface_id in modem_interfaces:
            modem_sms[interface_id] = await self.get_modem_sms(interface_id)

        return modem_sms

    async def api(self, method: str, endpoint: str, json: Mapping[str, Any] | None = {}):
        resp = await self.auth()
        return await self.reguest_api(method, endpoint, json)

    async def auth(self):
        response = await self.reguest_api("get", "/auth")
        if response.status == 401:
            password = f"{self._username}:{response.headers['X-NDM-Realm']}:{self._password}"
            password = md5(password.encode("utf-8"))
            password = response.headers["X-NDM-Challenge"] + password.hexdigest()
            password = sha256(password.encode("utf-8")).hexdigest()
            response = await self.reguest_api("post", "/auth", json={"login": self._username, "password": password})
            if response.status == 401:
                raise Exception(response)
        return response.status == 200

    async def components_list(self):
        return await self.api("post", "/rci/components/list")

    async def release_notes(self, version: str, channel: str = "dev"):
        return await self.api("post", "/rci/webhelp/release-notes", {"version":f"{version}","locale":"ru","channel":f"{channel}"})

    async def show_identification(self):
        return await self.api("get", "/rci/show/identification")

    async def async_reboot(self):
        return await self.api("post", "/rci/system/reboot", {})

    async def async_update(self):
        return await self.api("post", "/rci/components/commit", {"reason": "manual"})

    async def async_backup(self, folder: str, type_fw: list = ["firmware", "config"]):
        if "firmware" in type_fw:
            await self.async_download_file(f"{self.url_router}/ci/firmware", folder)
        if "config" in type_fw:
            await self.async_download_file(f"{self.url_router}/ci/startup-config", folder)
        return True

    async def show_system(self):
        return await self.api("get", "/rci/show/system")

    async def show_system_mode(self):
        return await self.api("get", "/rci/show/system/mode")

    async def show_version(self):
        return await self.api("get", "/rci/show/version")

    async def ndm_components(self):
        return await self.api("get", "/ndmComponents.js")

    async def show_ip_hotspot(self):
        return await self.api("get", "/rci/show/ip/hotspot/host")

    async def show_interface(self):
        return await self.api("get", "/rci/show/interface")

    async def show_rc_interface(self):
        interfaces = await self.api("get", "/rci/show/rc/interface")
        interface_wifi = {}
        for interface, interf in interfaces.items():
            if (
                interf.get("authentication", False) 
                and interf.get("authentication").get("wpa-psk", False)
                and interf.get("authentication").get("wpa-psk").get("psk", False)
                ):
                psw = interf["authentication"]["wpa-psk"]["psk"]
            else:
                psw = None
            if not interf.get('ssid', False):
                nm_inerface = interface
            else:
                nm_inerface = (f"{INTERFACES_WIFI_NAME.get(interface.split('/')[0], interface)}" % interf.get('ssid', "nameless"))
            interface_wifi[interface] = DataRcInterface(
                                                        interface,
                                                        nm_inerface,
                                                        interface.split('/')[0],
                                                        interf.get("ssid", False),
                                                        psw,
                                                        interf.get("up", False),
                                                        interf.get("rename", None),
                                                        interf.get("description", None),
            )
        return interface_wifi

    async def show_associations(self):
        return await self.api("get", "/rci/show/associations")

    async def show_interface_stat(self, interface: str):
        return await self.api("get", f"/rci/show/interface/stat?name={interface}")

    async def show_rc_interface_ip_global(self):
        return await self.api("get", f"/rci/show/rc/interface/ip/global")

    async def ip_hotspot_host_list(self):
        return await self.api("get", "/rci/ip/hotspot/host")

    async def ip_policy_list(self):
        return await self.api("get", "/rci/ip/policy")

    async def ip_hotspot_host_policy(self, mac: str, access: str = "permit", policy: str = {"no": True}):
        data_send = {"mac": mac, access: True, "policy": policy}
        return await self.api("post", "/rci/ip/hotspot/host", data_send)

    async def turn_on_off_interface(self, interface: str, state: str):
        return await self.api("post", f"/rci/interface/{interface}", {state: "true"})

    async def turn_on_off_port_forwarding(self, port_forwarding: str, state: bool):
        data_send = [
            {
                "ip": {
                    "index": port_forwarding,
                    "static": {
                        "disable": not state
                    }
                }
            },
            {"system": {"configuration": {"save": {}}}}
        ]
        return await self.api("post", f"/rci/", data_send)

    async def turn_on_off_web_configurator_access(self, state: bool):
        data_send = {"public": True, "ssl": True} if state else {"private": True}
        return await self.api("post", f"/rci/ip/http/security-level", data_send)

    async def turn_on_off_usb(self, state: bool, port: int):
        data_send = {"port": port, "power": {"shutdown": not state}}
        return await self.api("post", f"/rci/system/usb", data_send)

    def data_parser(self, data):
        new_data = {}
        data = data.replace('\n\t', '').replace('\n', '')
        data = data.split(';')
        for row in data:
            if row != '':
                row = row.split('=')
                nu = row[0].rstrip()
                te = row[1].lstrip()
                if '{' not in te:
                    te = te.replace('"', '')
                new_data[nu] = te
        return new_data

    async def show_stat_interface(self, stat_interfaces: list = None):
        stat_interfaces = stat_interfaces or self.request_interface
        data_json_send=[]
        for row in stat_interfaces:
            data_json_send.append({"show": {"interface": {"stat": {"name": row}}}})
        data_show_stat_interface = await self.api("post", "/rci/", json=data_json_send)
        # _LOGGER.debug(f"{self._mac} data_show_stat_interface {data_show_stat_interface} ")
        stat_interface={}
        for idx, row in enumerate(stat_interfaces):
            stat_interface[row] = data_show_stat_interface[idx]['show']['interface']['stat']
        return stat_interface

    async def custom_request(self):
        data_json_send=[]
        data_json_send.append({"show": {"system": {}}},)
        data_json_send.append({"show": {"interface": {}}})
        data_json_send.append({"show": {"associations": {}}})
        data_json_send.append({"show": {"rc": {"system": {}}}})
        data_json_send.append({"show": {"rc": {"ip": {"http": {}}}}})
        data_json_send.append({"show": {"media": {}}})

        if self.hw_type == "router":
            data_json_send.append({"show": {"ip": {"hotspot": {}}}})
            data_json_send.append({"show": {"rc": {"interface": {"ip": {"global": {}}}}}})
            data_json_send.append({"show": {"rc": {"ip": {"static": {}}}}})
            data_json_send.append({"show": {"rc": {"ip": {"hotspot": {}}}}})

        full_info_other = await self.api("post", "/rci/", json=data_json_send)

        show_system = full_info_other[0]['show']['system']
        fw_branch = show_system.get('sandbox', 'stable')
        show_interface = full_info_other[1]['show']['interface']
        show_associations = full_info_other[2]['show']['associations']
        show_rc_system_usb = full_info_other[3]['show']['rc']['system'].get('usb', [])
        show_rc_ip_http = full_info_other[4]['show']['rc']['ip']['http']
        show_media = full_info_other[5]['show'].get('media', {})
        show_modem_sms = {}

        show_ip_hotspot = {}
        show_rc_ip_static = {}
        show_ip_hotspot_policy = {}
        priority_interface = {}

        self._fw_branch = fw_branch

        if self.hw_type == "router":
            data_show_ip_hotspot = full_info_other[6]['show']['ip']['hotspot']['host']
            for hotspot in data_show_ip_hotspot:
                show_ip_hotspot[hotspot["mac"]] = DataDevice(
                    hotspot.get('mac'), 
                    hotspot.get('name'), 
                    hotspot.get('hostname'), 
                    hotspot.get('ip'), 
                    hotspot.get('active'), 
                    hotspot.get('interface', {"id": None}).get('id'),
                    hotspot.get('uptime'), 
                    hotspot.get('rssi'), 
                    hotspot.get('rxbytes'), 
                    hotspot.get('txbytes'), 
                )
            
            priority_interface = full_info_other[7]['show']['rc']['interface']['ip']['global']

            data_show_rc_ip_static = full_info_other[8]['show']['rc']['ip']['static']
            for port_frw in data_show_rc_ip_static:
                nm_pfrw = port_frw.get('comment', port_frw.get('index'))
                nm_pfrw = nm_pfrw if nm_pfrw != "" else port_frw.get('index')
                show_rc_ip_static[port_frw["index"]] = DataPortForwarding(
                    nm_pfrw, 
                    port_frw.get('interface'), 
                    port_frw.get('protocol'), 
                    port_frw.get('port'), 
                    port_frw.get('end-port', port_frw.get('port')), 
                    port_frw.get('to-host'), 
                    port_frw.get('index'), 
                    port_frw.get('comment', None), 
                    port_frw.get('disable', False), 
                )

            data_show_ip_hotspot_policy = full_info_other[9]['show']['rc']['ip']['hotspot']['host']
            for hotspot_pl in data_show_ip_hotspot_policy:
                show_ip_hotspot_policy[hotspot_pl["mac"]] = hotspot_pl

            try:
                show_modem_sms = await self.get_all_modem_sms(show_interface)
            except Exception as ex:
                _LOGGER.debug("%s unable to load modem sms: %s", self._mac, ex)

        stat_interface = await self.show_stat_interface()

        return KeeneticFullData(
            show_system,
            show_ip_hotspot, 
            show_interface, 
            show_rc_ip_static, 
            show_associations, 
            show_ip_hotspot_policy,
            priority_interface,
            show_rc_ip_http,
            show_rc_system_usb,
            show_media,
            stat_interface,
            show_modem_sms,
            )
