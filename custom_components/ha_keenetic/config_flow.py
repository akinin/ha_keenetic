"""The Keenetic API Config flow."""

import logging
import voluptuous as vol
from typing import Any
import operator

from homeassistant import config_entries
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import format_mac
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_SCAN_INTERVAL,
    CONF_SSL,
    CONF_VERIFY_SSL,
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
    CONF_CLIENTS_SELECT_POLICY,
    CONF_CREATE_ALL_CLIENTS_POLICY,
    CONF_CREATE_IMAGE_QR,
    CONF_SELECT_WIFI_QR,
    CONF_CREATE_DT,
    CONF_CREATE_PORT_FRW,
    DEFAULT_BACKUP_TYPE_FILE,
    CONF_BACKUP_TYPE_FILE,
    CONF_SELECT_CREATE_DT,
    CONF_MQTT_PUBLISH_SMS,
    CONF_MQTT_TOPIC_BASE,
    DEFAULT_MQTT_TOPIC_BASE,
    CONF_MQTT_OPENCLAW_COMPAT,
    CONF_MQTT_OPENCLAW_INBOUND_TOPIC,
    CONF_MQTT_OPENCLAW_DEFAULT_SENDER,
    CONF_MQTT_OPENCLAW_OUTBOUND_BRIDGE,
    CONF_MQTT_OPENCLAW_OUTBOUND_TOPIC,
    CONF_SMS_PUBLISH_WHITELIST,
    DEFAULT_MQTT_OPENCLAW_INBOUND_TOPIC,
    DEFAULT_MQTT_OPENCLAW_OUTBOUND_TOPIC,
    DEFAULT_MQTT_OPENCLAW_DEFAULT_SENDER,
    CONF_ENABLE_SMS,
    CONF_SMS_INTERFACE,
    CONF_SMS_SSH_PORT,
    DEFAULT_SMS_SSH_PORT,
)

_LOGGER = logging.getLogger(__name__)


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

    async def async_step_user(self, user_input=None):
        errors = {}
        title = ""
        if user_input is not None:
            try:
                router = await get_api(self.hass, user_input)
                keen = await router.show_version()

                title = f"{keen['vendor']} {keen['model']} {user_input['host']}"

            except Exception as error:
                _LOGGER.error('Keenetic Api Integration Exception - {}'.format(error))
                errors['base'] = str(error)
            if title != "":
                unique_id: str = f"{keen['vendor']} {keen['device']} {format_mac(router.mac).replace(':', '')}"
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return OptionsFlow(config_entry)


class OptionsFlow(config_entries.OptionsFlow):

    def __init__(self, config_entry):
        #self.config_entry = config_entry
        self._options = dict(config_entry.options)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if self.config_entry.entry_id not in self.hass.data[DOMAIN]:
            return self.async_abort(reason="integration_not_setup")
        self.router = self.hass.data[DOMAIN][self.config_entry.entry_id][COORD_FULL].router

        if self.router.hw_type != "router":
            return await self.async_step_configure_other()

        return await self.async_step_configure_router()


    async def async_step_configure_router(
        self, 
        user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            self._options.update(user_input)
            return self.async_create_entry(title="", data=self._options)

        data_clients = await self.router.show_ip_hotspot()
        _LOGGER.debug(f'CONF_CLIENTS_SELECT_POLICY - {self._options.get(CONF_CLIENTS_SELECT_POLICY, [])}')
        clients = {
            client['mac']: f"{client['name'] or client['hostname']} ({client['mac']})"
            for client in data_clients
        }
        clients_policy = clients
        clients_policy |= {
            mac: f"Unknown ({mac})"
            for mac in self._options.get(CONF_CLIENTS_SELECT_POLICY, [])
            if mac not in clients
        }
        clients_dt = clients
        clients_dt |= {
            mac: f"Unknown ({mac})"
            for mac in self._options.get(CONF_SELECT_CREATE_DT, [])
            if mac not in clients
        }

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
            step_id="configure_router",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self._options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    ): vol.All(cv.positive_int, vol.Clamp(min=MIN_SCAN_INTERVAL)),
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
                    vol.Optional(
                        CONF_ENABLE_SMS,
                        default=self._options.get(CONF_ENABLE_SMS, False),
                    ): bool,
                    vol.Optional(
                        CONF_SMS_INTERFACE,
                        default=self._options.get(CONF_SMS_INTERFACE, ""),
                    ): cv.string,
                    vol.Optional(
                        CONF_SMS_SSH_PORT,
                        default=self._options.get(CONF_SMS_SSH_PORT, DEFAULT_SMS_SSH_PORT),
                    ): vol.All(cv.positive_int, vol.Clamp(min=1, max=65535)),
                    vol.Optional(
                        CONF_MQTT_PUBLISH_SMS,
                        default=self._options.get(CONF_MQTT_PUBLISH_SMS, False),
                    ): bool,
                    vol.Optional(
                        CONF_MQTT_TOPIC_BASE,
                        default=self._options.get(CONF_MQTT_TOPIC_BASE, DEFAULT_MQTT_TOPIC_BASE),
                    ): cv.string,
                    vol.Optional(
                        CONF_MQTT_OPENCLAW_COMPAT,
                        default=self._options.get(CONF_MQTT_OPENCLAW_COMPAT, False),
                    ): bool,
                    vol.Optional(
                        CONF_MQTT_OPENCLAW_INBOUND_TOPIC,
                        default=self._options.get(
                            CONF_MQTT_OPENCLAW_INBOUND_TOPIC,
                            DEFAULT_MQTT_OPENCLAW_INBOUND_TOPIC,
                        ),
                    ): cv.string,
                    vol.Optional(
                        CONF_MQTT_OPENCLAW_DEFAULT_SENDER,
                        default=self._options.get(
                            CONF_MQTT_OPENCLAW_DEFAULT_SENDER,
                            DEFAULT_MQTT_OPENCLAW_DEFAULT_SENDER,
                        ),
                    ): cv.string,
                    vol.Optional(
                        CONF_MQTT_OPENCLAW_OUTBOUND_BRIDGE,
                        default=self._options.get(CONF_MQTT_OPENCLAW_OUTBOUND_BRIDGE, False),
                    ): bool,
                    vol.Optional(
                        CONF_MQTT_OPENCLAW_OUTBOUND_TOPIC,
                        default=self._options.get(
                            CONF_MQTT_OPENCLAW_OUTBOUND_TOPIC,
                            DEFAULT_MQTT_OPENCLAW_OUTBOUND_TOPIC,
                        ),
                    ): cv.string,
                    vol.Optional(
                        CONF_SMS_PUBLISH_WHITELIST,
                        default=self._options.get(CONF_SMS_PUBLISH_WHITELIST, ""),
                    ): cv.string,
                }
            ),
            last_step=False,
        )

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
                    ): vol.All(cv.positive_int, vol.Clamp(min=MIN_SCAN_INTERVAL)),
                    vol.Optional(
                        CONF_ENABLE_SMS,
                        default=self._options.get(CONF_ENABLE_SMS, False),
                    ): bool,
                    vol.Optional(
                        CONF_SMS_INTERFACE,
                        default=self._options.get(CONF_SMS_INTERFACE, ""),
                    ): cv.string,
                    vol.Optional(
                        CONF_SMS_SSH_PORT,
                        default=self._options.get(CONF_SMS_SSH_PORT, DEFAULT_SMS_SSH_PORT),
                    ): vol.All(cv.positive_int, vol.Clamp(min=1, max=65535)),
                    vol.Optional(
                        CONF_MQTT_PUBLISH_SMS,
                        default=self._options.get(CONF_MQTT_PUBLISH_SMS, False),
                    ): bool,
                    vol.Optional(
                        CONF_MQTT_TOPIC_BASE,
                        default=self._options.get(CONF_MQTT_TOPIC_BASE, DEFAULT_MQTT_TOPIC_BASE),
                    ): cv.string,
                    vol.Optional(
                        CONF_MQTT_OPENCLAW_COMPAT,
                        default=self._options.get(CONF_MQTT_OPENCLAW_COMPAT, False),
                    ): bool,
                    vol.Optional(
                        CONF_MQTT_OPENCLAW_INBOUND_TOPIC,
                        default=self._options.get(
                            CONF_MQTT_OPENCLAW_INBOUND_TOPIC,
                            DEFAULT_MQTT_OPENCLAW_INBOUND_TOPIC,
                        ),
                    ): cv.string,
                    vol.Optional(
                        CONF_MQTT_OPENCLAW_DEFAULT_SENDER,
                        default=self._options.get(
                            CONF_MQTT_OPENCLAW_DEFAULT_SENDER,
                            DEFAULT_MQTT_OPENCLAW_DEFAULT_SENDER,
                        ),
                    ): cv.string,
                    vol.Optional(
                        CONF_MQTT_OPENCLAW_OUTBOUND_BRIDGE,
                        default=self._options.get(CONF_MQTT_OPENCLAW_OUTBOUND_BRIDGE, False),
                    ): bool,
                    vol.Optional(
                        CONF_MQTT_OPENCLAW_OUTBOUND_TOPIC,
                        default=self._options.get(
                            CONF_MQTT_OPENCLAW_OUTBOUND_TOPIC,
                            DEFAULT_MQTT_OPENCLAW_OUTBOUND_TOPIC,
                        ),
                    ): cv.string,
                    vol.Optional(
                        CONF_SMS_PUBLISH_WHITELIST,
                        default=self._options.get(CONF_SMS_PUBLISH_WHITELIST, ""),
                    ): cv.string,
                }
            ),
            last_step=False,
        )
