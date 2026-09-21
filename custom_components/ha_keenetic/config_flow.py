"""The Keenetic API Config flow."""

import logging
import voluptuous as vol
from typing import Any
import operator
from urllib.parse import urlparse

from homeassistant import config_entries
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.service_info.ssdp import SsdpServiceInfo
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_SSL,
    CONF_USERNAME,
    CONF_PORT,
)

from . import get_api
from .const import (
    DOMAIN,
    COORD_FULL,
    COORD_RC_INTERFACE,
)
from .keenetic import Router
from .const import (
    DEFAULT_SCAN_INTERVAL, 
    MIN_SCAN_INTERVAL,
    CONF_SENSOR_GROUPS,
    CONF_ROUTER_SERIAL,
    CONF_CLIENTS_SELECT_POLICY,
    CONF_CREATE_ALL_CLIENTS_POLICY,
    CONF_CREATE_IMAGE_QR,
    CONF_SELECT_WIFI_QR,
    CONF_CREATE_DT,
    CONF_CREATE_PORT_FRW,
    DEFAULT_BACKUP_TYPE_FILE,
    DEFAULT_SENSOR_GROUPS,
    CONF_BACKUP_TYPE_FILE,
    CONF_SELECT_CREATE_DT,
    SENSOR_GROUP_INTERFACE,
    SENSOR_GROUP_MESH,
    SENSOR_GROUP_ROUTER,
    SENSOR_GROUP_STORAGE,
    SENSOR_GROUP_WIFI,
)

_LOGGER = logging.getLogger(__name__)


def _host_from_address(address: str | None) -> str | None:
    """Extract a host from either a URL or a bare host in an existing entry."""
    if not address:
        return None
    parsed = urlparse(address if "://" in address else f"//{address}")
    return parsed.hostname.lower() if parsed.hostname else None


def _matches_authenticated_router(
    entry_unique_id: str | None, legacy_unique_id: str, serial_number: str | None
) -> bool:
    """Match both legacy MAC and SSDP-serial config entries after login."""
    return bool(
        entry_unique_id
        and (
            entry_unique_id == legacy_unique_id
            or (serial_number and entry_unique_id == serial_number)
        )
    )


def _same_serial(left: str | None, right: str | None) -> bool:
    """Compare serials without depending on SSDP capitalization."""
    return bool(left and right and str(left).strip().casefold() == str(right).strip().casefold())


def _update_discovered_host(hass, entry, hostname: str) -> None:
    """Follow a router's new address without changing its scheme or port."""
    old_address = entry.data.get(CONF_HOST)
    if not old_address or _host_from_address(old_address) == hostname.lower():
        return
    parsed = urlparse(old_address if "://" in old_address else f"//{old_address}")
    scheme = parsed.scheme or ("https" if entry.data.get(CONF_SSL) else "http")
    host = f"[{hostname}]" if ":" in hostname else hostname
    userinfo = parsed.netloc.rpartition("@")[0] + "@" if "@" in parsed.netloc else ""
    netloc = f"{userinfo}{host}"
    if parsed.port is not None:
        netloc += f":{parsed.port}"
    new_address = parsed._replace(scheme=scheme, netloc=netloc).geturl()
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, CONF_HOST: new_address},
    )


STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME, default='admin'): cv.string,
        vol.Required(CONF_PASSWORD, default=''): cv.string,
        vol.Required(CONF_HOST, default='http://192.168.1.1'): str,
        vol.Required(CONF_PORT, default=80): int,
        vol.Required(CONF_SSL, default=False): bool,
    }
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Keenetic."""

    async def async_step_ssdp(self, discovery_info: SsdpServiceInfo) -> FlowResult:
        """Handle SSDP discovery."""
        manufacturer = (discovery_info.upnp.get("manufacturer") or "").lower()
        if "keenetic" not in manufacturer and "zyxel" not in manufacturer:
            return self.async_abort(reason="not_keenetic")

        hostname = urlparse(discovery_info.ssdp_location).hostname
        if hostname is None:
            return self.async_abort(reason="no_host")

        serial = discovery_info.upnp.get("serialNumber")
        udn = discovery_info.upnp.get("UDN")
        self._discovered_serial = serial
        discovery_id = serial or udn
        if discovery_id:
            await self.async_set_unique_id(discovery_id)
            # A router configured from SSDP already uses this exact ID. Keep
            # its scheme and port while following a changed DHCP address.
            configured_entry = next(
                (
                    entry for entry in self._async_current_entries()
                    if entry.unique_id == discovery_id
                ),
                None,
            )
            if configured_entry is not None and configured_entry.data.get(CONF_HOST):
                _update_discovered_host(self.hass, configured_entry, hostname)
                return self.async_abort(reason="already_configured")
            self._abort_if_unique_id_configured()
        else:
            # A host address is not a stable device identity. Let Home
            # Assistant handle discovery without a unique ID instead.
            await self._async_handle_discovery_without_unique_id()

        # Entries created by older releases use a MAC-based unique ID, so the
        # SSDP serial/UDN above cannot match them. Prefer the serial read from
        # the authenticated router; fall back to an unchanged host only when
        # SSDP omits its serial or the entry has no stored serial yet.
        for entry in self._async_current_entries():
            stored_serial = entry.data.get(CONF_ROUTER_SERIAL)
            if _same_serial(stored_serial, serial):
                _update_discovered_host(self.hass, entry, hostname)
                return self.async_abort(reason="already_configured")
            if (
                (not serial or not stored_serial)
                and _host_from_address(entry.data.get(CONF_HOST)) == hostname.lower()
            ):
                return self.async_abort(reason="already_configured")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default="admin"): cv.string,
                    vol.Required(CONF_PASSWORD, default=""): cv.string,
                    vol.Required(CONF_HOST, default=f"http://{hostname}"): str,
                    vol.Required(CONF_PORT, default=80): int,
                    vol.Required(CONF_SSL, default=False): bool,
                }
            ),
            description_placeholders={
                "name": discovery_info.upnp.get("friendlyName", "Keenetic Router"),
                "host": hostname,
            },
        )

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        title = ""
        if user_input is not None:
            try:
                router = await get_api(self.hass, user_input)
                keen = await router.show_version()

                discovered_serial = getattr(self, "_discovered_serial", None)
                if discovered_serial and router.serial_number and not _same_serial(
                    discovered_serial, router.serial_number
                ):
                    # The host in the SSDP form is editable. Never assign the
                    # discovered router's identity to a different router.
                    _LOGGER.warning(
                        "SSDP router serial differs from the authenticated router"
                    )
                    errors["base"] = "cannot_connect"
                    return self.async_show_form(
                        step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
                    )

                title = f"{keen['vendor']} {keen['model']} {user_input['host']}"

            except Exception as error:
                _LOGGER.error('Keenetic Api Integration Exception - {}'.format(error))
                errors['base'] = str(error)
            if title != "":
                legacy_unique_id: str = f"{keen['vendor']} {keen['device']} {format_mac(router.mac).replace(':', '')}"
                serial_number = router.serial_number or None

                # A discovered flow already has a stable SSDP ID. Do not
                # replace it with the historical MAC-based ID when the user
                # submits the credentials form.
                for entry in self._async_current_entries():
                    if (
                        _matches_authenticated_router(
                            entry.unique_id, legacy_unique_id, serial_number
                        )
                        or _same_serial(entry.data.get(CONF_ROUTER_SERIAL), serial_number)
                    ):
                        if self.source == config_entries.SOURCE_SSDP:
                            # Authentication proved this is the same router,
                            # even if DHCP changed its host. Keep all existing
                            # entity IDs by preserving the config entry ID.
                            updated_data = {**entry.data, **user_input}
                            if serial_number:
                                updated_data[CONF_ROUTER_SERIAL] = serial_number
                            if updated_data != entry.data:
                                self.hass.config_entries.async_update_entry(
                                    entry, data=updated_data
                                )
                        return self.async_abort(reason="already_configured")

                if self.unique_id is None:
                    await self.async_set_unique_id(legacy_unique_id)
                self._abort_if_unique_id_configured()
                entry_data = dict(user_input)
                if serial_number:
                    entry_data[CONF_ROUTER_SERIAL] = serial_number
                return self.async_create_entry(title=title, data=entry_data)

        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return OptionsFlow(config_entry)


class OptionsFlow(config_entries.OptionsFlow):
    """Handle a options flow for Keenetic."""

    def __init__(self, config_entry):
        """Initialize Keenetic options flow."""
        #self.config_entry = config_entry
        self._data = dict(config_entry.data)
        self._options = dict(config_entry.options)
        self.router: Router | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        integration_data = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        if integration_data is None:
            return self.async_show_menu(
                step_id="init",
                menu_options=[
                    "configure_connection",
                    "save",
                ],
            )

        self.router = integration_data[COORD_FULL].router

        if self.router.hw_type != "router":
            return await self.async_step_configure_other()

        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "configure_connection",
                "configure_general",
                "configure_sensors",
                "configure_wifi",
                "configure_clients",
                "configure_features",
                "save",
            ],
        )

    async def async_step_configure_connection(
        self,
        user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            new_data = dict(self._data)
            new_data.update(user_input)
            try:
                await get_api(self.hass, new_data)
            except Exception as error:
                _LOGGER.error("Keenetic connection settings validation failed: %s", error)
                errors["base"] = "cannot_connect"
            else:
                self._data = new_data
                return await self.async_step_init()

        return self.async_show_form(
            step_id="configure_connection",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST,
                        default=self._data.get(CONF_HOST, "http://192.168.1.1"),
                    ): str,
                    vol.Required(
                        CONF_PORT,
                        default=self._data.get(CONF_PORT, 80),
                    ): int,
                    vol.Required(
                        CONF_USERNAME,
                        default=self._data.get(CONF_USERNAME, "admin"),
                    ): cv.string,
                    vol.Required(
                        CONF_PASSWORD,
                        default=self._data.get(CONF_PASSWORD, ""),
                    ): cv.string,
                    vol.Required(
                        CONF_SSL,
                        default=self._data.get(CONF_SSL, False),
                    ): bool,
                }
            ),
            errors=errors,
        )


    async def async_step_configure_general(
        self,
        user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_init()

        coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id][COORD_FULL]
        router = coordinator.router
        system = coordinator.data.show_system

        return self.async_show_form(
            step_id="configure_general",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self._options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.All(cv.positive_int, vol.Clamp(min=MIN_SCAN_INTERVAL)),
                }
            ),
            description_placeholders={
                "model": router.model or "Keenetic",
                "host": self._data.get(CONF_HOST, ""),
                "mode": getattr(router, "hw_type", ""),
                "uptime": str(system.get("uptime", "")),
                "clients": str(len(coordinator.data.show_ip_hotspot)),
            },
        )

    async def async_step_configure_sensors(
        self,
        user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_init()

        if (self.hass.config.language or "").startswith("ru"):
            sensor_groups = {
                SENSOR_GROUP_ROUTER: "Диагностика роутера",
                SENSOR_GROUP_INTERFACE: "Трафик интерфейсов",
                SENSOR_GROUP_WIFI: "Wi-Fi радио",
                SENSOR_GROUP_STORAGE: "Накопители",
                SENSOR_GROUP_MESH: "Mesh",
            }
        else:
            sensor_groups = {
                SENSOR_GROUP_ROUTER: "Router diagnostics",
                SENSOR_GROUP_INTERFACE: "Interface traffic",
                SENSOR_GROUP_WIFI: "Wi-Fi radio",
                SENSOR_GROUP_STORAGE: "Storage",
                SENSOR_GROUP_MESH: "Mesh",
            }

        return self.async_show_form(
            step_id="configure_sensors",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SENSOR_GROUPS,
                        default=self._options.get(CONF_SENSOR_GROUPS, DEFAULT_SENSOR_GROUPS),
                    ): cv.multi_select(sensor_groups),
                }
            ),
        )

    async def async_step_configure_wifi(
        self,
        user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_init()

        wifi_interfaces = {}
        try:
            if COORD_RC_INTERFACE in self.hass.data[DOMAIN][self.config_entry.entry_id]:
                rc_interfaces = self.hass.data[DOMAIN][self.config_entry.entry_id][COORD_RC_INTERFACE].data
                for interface_id, interface_data in rc_interfaces.items():
                    if (hasattr(interface_data, 'ssid') and 
                        interface_data.ssid and 
                        interface_data.interface in ['WifiMaster0', 'WifiMaster1']):
                        wifi_interfaces[interface_id] = f"{interface_data.name_interface}"
        except Exception as e:
            _LOGGER.error(f"Error getting WiFi interfaces: {e}")
        
        wifi_interfaces |= {
            interface_id: f"Unknown ({interface_id})"
            for interface_id in self._options.get(CONF_SELECT_WIFI_QR, [])
            if interface_id not in wifi_interfaces
        }

        return self.async_show_form(
            step_id="configure_wifi",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_CREATE_IMAGE_QR,
                        default=self._options.get(
                            CONF_CREATE_IMAGE_QR, False
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_SELECT_WIFI_QR,
                        default=self._options.get(CONF_SELECT_WIFI_QR, []),
                    ): cv.multi_select(
                        dict(sorted(wifi_interfaces.items(), key=operator.itemgetter(1)))
                    ),
                }
            ),
        )

    async def async_step_configure_clients(
        self,
        user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_init()

        data_clients = await self.router.show_ip_hotspot()
        _LOGGER.debug(f'CONF_CLIENTS_SELECT_POLICY - {self._options.get(CONF_CLIENTS_SELECT_POLICY, [])}')
        clients = {
            client["mac"]: f"{client.get('name') or client.get('hostname') or 'Unknown'} ({client['mac']})"
            for client in data_clients
        }
        clients_policy = dict(clients)
        clients_policy |= {
            mac: f"Unknown ({mac})"
            for mac in self._options.get(CONF_CLIENTS_SELECT_POLICY, [])
            if mac not in clients
        }
        clients_dt = dict(clients)
        clients_dt |= {
            mac: f"Unknown ({mac})"
            for mac in self._options.get(CONF_SELECT_CREATE_DT, [])
            if mac not in clients
        }

        return self.async_show_form(
            step_id="configure_clients",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_CREATE_ALL_CLIENTS_POLICY,
                        default=self._options.get(
                            CONF_CREATE_ALL_CLIENTS_POLICY, False
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_CLIENTS_SELECT_POLICY,
                        default=self._options.get(CONF_CLIENTS_SELECT_POLICY, []),
                    ): cv.multi_select(
                        dict(sorted(clients_policy.items(), key=operator.itemgetter(1)))
                    ),
                    vol.Optional(
                        CONF_CREATE_DT,
                        default=self._options.get(
                            CONF_CREATE_DT, False
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_SELECT_CREATE_DT,
                        default=self._options.get(CONF_SELECT_CREATE_DT, []),
                    ): cv.multi_select(
                        dict(sorted(clients_dt.items(), key=operator.itemgetter(1)))
                    ),
                }
            ),
        )

    async def async_step_configure_features(
        self,
        user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_init()

        return self.async_show_form(
            step_id="configure_features",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_CREATE_PORT_FRW,
                        default=self._options.get(
                            CONF_CREATE_PORT_FRW, False
                        ),
                    ): bool,
                    vol.Optional(
                        CONF_BACKUP_TYPE_FILE,
                        default=self._options.get(CONF_BACKUP_TYPE_FILE, DEFAULT_BACKUP_TYPE_FILE),
                    ): cv.multi_select([
                        "config",
                        "firmware",
                    ]),
                }
            ),
        )

    async def async_step_configure_router(
        self,
        user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Keep backward-compatible entry point for older options flows."""
        if user_input is not None:
            self._options.update(user_input)
            return self.async_create_entry(title="", data=self._options)
        return await self.async_step_init(user_input)

    async def async_step_save(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Save collected options."""
        if self._data != dict(self.config_entry.data):
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=self._data,
            )
        return self.async_create_entry(title="", data=self._options)

    async def async_step_configure_other(
        self,
        user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            self._options.update(user_input)
            return self.async_create_entry(title="", data=self._options)

        return self.async_show_form(
            step_id="configure_other",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self._options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.All(cv.positive_int, vol.Clamp(min=MIN_SCAN_INTERVAL))
                }
            ),
            last_step=False,
        )
