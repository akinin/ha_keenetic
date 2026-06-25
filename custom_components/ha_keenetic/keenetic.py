"""The Keenetic API."""

from __future__ import annotations
from hashlib import md5, sha256
from collections.abc import Mapping
from typing import Literal, Any
import asyncio
import aiohttp
import logging
import aiofiles.os
from pathlib import Path
from dataclasses import dataclass

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
    show_pingcheck: dict[str, Any]

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
    idle_timeout: int

@dataclass
class DataPingCheck():
    interface_name: str
    status: str

CONFIG_SAVE = {"system": {"configuration": {"save": {}}}}


INTERFACES_WIFI_NAME = {
    "WifiMaster0": "WiFi %s 2.4G",
    "WifiMaster1": "WiFi %s 5G",
}

INTERFACES_WIFI_NAME_LIST = {
    "WifiMaster0": "WiFi 2.4G",
    "WifiMaster1": "WiFi 5G",
}

LIST_INTERFACES = [
    "UsbModem",
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
    "TunnelSixInFour",
    "SSTPEthernet",
    "Proxy",
    "IPIP",
    "IKE",
    "Gre",
    "MapT",
    "DsLite",
    "UsbQmi",
]

LIST_INTERFACES_PUBLIC = [
    "GigabitEthernet",
    "Ethernet",
]

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

        self._mac = ""
        self._serial_number = ""
        self._model = ""
        self._hw_type = ""
        self._hw_id = ""
        self._name_device = ""
        self._fw_branch = None
        self._usb = []

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
    @property
    def usb(self):
        return self._usb


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
        self._usb = data_show_system.get("usb", [])

        try:
            data_show_rc_system = await self.show_rc_system()
            self._usb = data_show_rc_system.get("usb", self._usb)
        except Exception as err:
            _LOGGER.debug("%s could not read rc/system usb info: %s", self._mac, err)

        data_show_system_mode = await self.show_system_mode()
        self._hw_type = data_show_system_mode["active"]

        if self._hw_type == "router":
            # data_show_rc_interface_ip_global = await self.show_rc_interface_ip_global()
            data_show_interface = await self.show_interface()
            for interface, data_interface in data_show_interface.items():
                if (
                    (
                        data_interface.get('type', 'No') in LIST_INTERFACES
                    )
                    or
                    (
                        data_interface.get('type', 'No') in LIST_INTERFACES_PUBLIC
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
            # Получаем информацию об интерфейсах
            interfaces = await self.show_interface()
            
            # Создаем функцию для получения статистики по интерфейсу
            async def get_port_statistics(port_id):
                try:
                    stats = await self.show_interface_stat(port_id)
                    return stats
                except Exception as ex:
                    _LOGGER.error(f"Error getting statistics for port {port_id}: {ex}")
                    return {}
            
            # Импортируем процессор Ethernet портов и обрабатываем данные
            from .processor_ethernet import EthernetProcessor
            return await EthernetProcessor.process_ethernet_ports(interfaces, get_port_statistics)
        except Exception as ex:
            _LOGGER.error(f"Error processing ethernet ports: {ex}")
            return {}

    async def get_mesh_nodes(self):
        """Get information about mesh network nodes."""
        try:
            # Используем правильный API-путь для получения информации о Mesh-узлах
            mesh_info = await self.api("get", "/rci/show/mws/member")
            
            # Логируем для отладки
            _LOGGER.debug("Mesh network information from /rci/show/mws/member: %s", mesh_info)
            
            # Импортируем процессор Mesh-сети и обрабатываем данные
            from .processor_mesh import MeshProcessor
            return MeshProcessor.process_mesh_nodes(mesh_info)
        except Exception as ex:
            _LOGGER.error(f"Error processing mesh nodes: {ex}")
            return {}

    async def get_vpn_interfaces(self):
        """Get information about VPN interfaces."""
        try:
            # Получаем информацию об интерфейсах
            interfaces = await self.show_interface()
            
            # Логируем для отладки
            _LOGGER.debug("Available interfaces for VPN processing: %s", list(interfaces.keys()))
            
            # Дополнительно логируем интерфейсы, содержащие 'wireguard' или 'wg' в имени
            for interface_id, interface_data in interfaces.items():
                if 'wireguard' in interface_id.lower() or 'wg' in interface_id.lower():
                    _LOGGER.debug("Found potential WireGuard interface: %s, data: %s", interface_id, interface_data)
            
            # Создаем функцию для получения статистики по интерфейсу
            async def get_interface_statistics(interface_id):
                try:
                    stats = await self.show_interface_stat(interface_id)
                    return stats
                except Exception as ex:
                    _LOGGER.error(f"Error getting statistics for interface {interface_id}: {ex}")
                    return {}
            
            # Импортируем процессор VPN интерфейсов и обрабатываем данные
            from .processor_vpn import VpnProcessor
            vpn_interfaces = await VpnProcessor.process_vpn_interfaces(interfaces, get_interface_statistics)
            
            # Логируем результат
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
                else:
                    result = res
                _LOGGER.debug(f'{self._mac} status - {endpoint} {res.status}')
        except asyncio.TimeoutError as err:
            raise Exception("TimeoutError") from err
        return result

    async def get_wifi_interfaces(self):
        """Get information about WiFi interfaces."""
        try:
            # Получаем информацию об интерфейсах
            interfaces = await self.show_interface()
            
            # Получаем информацию о RC интерфейсах
            rc_interfaces = await self.show_rc_interface()
            
            # Создаем функцию для получения информации о подключенных клиентах
            async def get_associations():
                try:
                    associations = await self.show_associations()
                    # Логируем тип и структуру данных для отладки
                    _LOGGER.debug(f"Associations type: {type(associations)}, data: {associations}")
                    return associations
                except Exception as ex:
                    _LOGGER.error(f"Error getting associations: {ex}")
                    return {}
            
            # Импортируем процессор WiFi интерфейсов и обрабатываем данные
            from .processor_wifi import WiFiProcessor
            return await WiFiProcessor.process_wifi_interfaces(interfaces, rc_interfaces, get_associations)
        except Exception as ex:
            _LOGGER.error(f"Error processing WiFi interfaces: {ex}")
            return {}

    async def get_usb_ports(self):
        """Get information about USB ports."""
        try:
            # Проверяем, есть ли данные о USB-портах в уже полученных данных
            usb_info = []
            
            if hasattr(self, 'data') and hasattr(self.data, 'show_rc_system_usb'):
                usb_info = self.data.show_rc_system_usb
                _LOGGER.debug(f"Using existing USB info from show_rc_system_usb: {usb_info}")
            
            # Если данных нет, пытаемся получить их напрямую
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
            
            # Если usb_info не список, преобразуем его
            if isinstance(usb_info, dict):
                usb_info = [usb_info]
            elif not isinstance(usb_info, list):
                usb_info = []
            
            # Создаем функцию для получения информации о медиа-устройствах
            async def get_media_info(media_name):
                try:
                    # Проверяем, что self.data и self.data.show_media существуют
                    if hasattr(self, 'data') and hasattr(self.data, 'show_media'):
                        media_info = self.data.show_media.get(media_name)
                        return media_info
                    return None
                except Exception as ex:
                    _LOGGER.error(f"Error getting media info for {media_name}: {ex}")
                    return None
            
            # Импортируем процессор USB портов и обрабатываем данные
            from .processor_usb import UsbProcessor
            return await UsbProcessor.process_usb_ports(usb_info, get_media_info)
        except Exception as ex:
            _LOGGER.error(f"Error processing USB ports: {ex}", exc_info=True)
            return {}

    async def api(self, method: str, endpoint: str, json: Mapping[str, Any] | None = None):
        await self.auth()
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
            interface_main = interface.split('/')[0]
            if (
                interf.get("authentication", False) 
                and interf.get("authentication").get("wpa-psk", False)
                and interf.get("authentication").get("wpa-psk").get("psk", False)
                ):
                psw = interf["authentication"]["wpa-psk"]["psk"]
            else:
                psw = None
            if interf.get('ssid', False):
                nm_inerface = (f"{INTERFACES_WIFI_NAME.get(interface_main, interface)}" % interf.get('ssid', "nameless"))
            elif "WifiMaster" in interface:
                nm_inerface = INTERFACES_WIFI_NAME_LIST.get(interface_main, interface)
            else:
                nm_inerface = interface
            interface_wifi[interface] = DataRcInterface(
                                                        interface,
                                                        nm_inerface,
                                                        interface_main,
                                                        interf.get("ssid", False),
                                                        psw,
                                                        interf.get("up", False),
                                                        interf.get("rename", None),
                                                        interf.get("description", None),
                                                        interf.get('idle-timeout', {}).get('idle-timeout', 600),
            )
        return interface_wifi

    async def show_associations(self):
        return await self.api("get", "/rci/show/associations")

    async def show_interface_stat(self, interface: str):
        return await self.api("get", f"/rci/show/interface/stat?name={interface}")

    async def show_rc_interface_ip_global(self):
        return await self.api("get", f"/rci/show/rc/interface/ip/global")

    async def show_rc_system(self):
        return await self.api("get", "/rci/show/rc/system")

    async def ip_hotspot_host_list(self):
        return await self.api("get", "/rci/ip/hotspot/host")

    async def ip_policy_list(self):
        return await self.api("get", "/rci/ip/policy")

    async def ip_hotspot_host_policy(self, mac: str, access: str = "permit", policy: str = {"no": True}):
        data_send = {"mac": mac, access: True, "policy": policy}
        return await self.api("post", "/rci/ip/hotspot/host", data_send)

    async def turn_on_off_interface(self, interface: str, state: str):
        data_send = [
            {"interface": {"name": interface, state: True}},
        ]
        if state == "up" and interface.startswith("WifiMaster") and "/" in interface:
            data_send.append({"interface": {"name": interface.split("/")[0], state: True}})
        data_send.append(CONFIG_SAVE)
        return await self.api("post", "/rci/", data_send)

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
            CONFIG_SAVE
        ]
        return await self.api("post", f"/rci/", data_send)

    async def turn_on_off_web_configurator_access(self, state: bool):
        data_send = {"public": True, "ssl": True} if state else {"private": True}
        return await self.api("post", f"/rci/ip/http/security-level", data_send)

    async def turn_on_off_usb(self, state: bool, port: int):
        data_send = {"port": port, "power": {"shutdown": not state}}
        return await self.api("post", f"/rci/system/usb", data_send)

    async def set_clients_idle_timeout_wifi(self, interface: str, timeout: int):
        if not 60 <= timeout <= 2147483646:
            raise ValueError(f"Value {timeout} must be in the range from 60 to 2147483646")
        data_send = [
            {"interface": {interface: {"idle-timeout": int(timeout)}}},
            CONFIG_SAVE,
        ]
        return await self.api("post", "/rci/", data_send)

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
        requests = [
            ("system", {"show": {"system": {}}}),
            ("interface", {"show": {"interface": {}}}),
            ("associations", {"show": {"associations": {}}}),
            ("rc_system", {"show": {"rc": {"system": {}}}}),
            ("rc_ip_http", {"show": {"rc": {"ip": {"http": {}}}}}),
        ]

        if self.hw_type == "router":
            requests.extend(
                [
                    ("ip_hotspot", {"show": {"ip": {"hotspot": {}}}}),
                    ("priority_interface", {"show": {"rc": {"interface": {"ip": {"global": {}}}}}}),
                    ("rc_ip_static", {"show": {"rc": {"ip": {"static": {}}}}}),
                    ("ip_hotspot_policy", {"show": {"rc": {"ip": {"hotspot": {}}}}}),
                    ("pingcheck", {"show": {"ping-check": {}}}),
                ]
            )

        if self.usb:
            requests.append(("media", {"show": {"media": {}}}))

        responses = await self.api("post", "/rci/", json=[payload for _, payload in requests])
        if not isinstance(responses, list):
            raise ValueError(f"Unexpected custom_request response: {responses}")

        response_map = dict(zip((name for name, _ in requests), responses, strict=False))

        show_system = response_map.get("system", {}).get('show', {}).get('system', {})
        fw_branch = show_system.get('sandbox', 'stable')
        show_interface = response_map.get("interface", {}).get('show', {}).get('interface', {})
        show_associations = response_map.get("associations", {}).get('show', {}).get('associations', {})
        show_rc_system_usb = response_map.get("rc_system", {}).get('show', {}).get('rc', {}).get('system', {}).get('usb', [])
        show_rc_ip_http = response_map.get("rc_ip_http", {}).get('show', {}).get('rc', {}).get('ip', {}).get('http', {})
        show_media = response_map.get("media", {}).get('show', {}).get('media', {})

        show_ip_hotspot = {}
        show_rc_ip_static = {}
        show_ip_hotspot_policy = {}
        priority_interface = {}
        show_pingcheck = {}

        self._fw_branch = fw_branch

        if self.hw_type == "router":
            data_show_ip_hotspot = response_map.get("ip_hotspot", {}).get('show', {}).get('ip', {}).get('hotspot', {}).get('host', [])
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
            
            priority_interface = response_map.get("priority_interface", {}).get('show', {}).get('rc', {}).get('interface', {}).get('ip', {}).get('global', {})

            data_show_rc_ip_static = response_map.get("rc_ip_static", {}).get('show', {}).get('rc', {}).get('ip', {}).get('static', [])
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

            data_show_ip_hotspot_policy = response_map.get("ip_hotspot_policy", {}).get('show', {}).get('rc', {}).get('ip', {}).get('hotspot', {}).get('host', [])
            for hotspot_pl in data_show_ip_hotspot_policy:
                show_ip_hotspot_policy[hotspot_pl["mac"]] = hotspot_pl

            data_show_pingcheck = response_map.get("pingcheck", {}).get('show', {}).get('ping-check', {}).get('pingcheck', [])
            for pingcheck in data_show_pingcheck:
                interfaces = pingcheck.get('interface')
                if not isinstance(interfaces, dict):
                    continue
                for interface, interface_data in interfaces.items():
                    show_pingcheck[interface] = DataPingCheck(
                        self.request_interface.get(interface, interface),
                        interface_data.get('status', 'not ready'),
                    )

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
            show_pingcheck,
            )
