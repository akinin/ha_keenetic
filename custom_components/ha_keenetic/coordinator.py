"""The Keenetic API coordinator."""

from __future__ import annotations
from datetime import timedelta
import logging
import asyncio
import json

from homeassistant.components.mqtt import async_publish as mqtt_async_publish
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator, 
    UpdateFailed,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.const import CONF_HOST
from homeassistant.config_entries import ConfigEntry

from .keenetic import Router
from .const import (
    DOMAIN, 
    FW_SANDBOX,
    COORD_FIREWARE,
    SCAN_INTERVAL_FIREWARE,
    COUNT_REPEATED_REQUEST_FIREWARE,
    TIMER_REPEATED_REQUEST_FIREWARE,
    EVENT_NEW_SMS,
    CONF_MQTT_PUBLISH_SMS,
    CONF_MQTT_TOPIC_BASE,
    DEFAULT_MQTT_TOPIC_BASE,
)

_LOGGER = logging.getLogger(__name__)


class KeeneticRouterCoordinator(DataUpdateCoordinator):
    def __init__(
            self,
            hass: HomeAssistant,
            router: Router,
            update_interval: int,
            entry: ConfigEntry
    ) -> None:
        self.router = router
        self.entry = entry
        self._host = entry.data[CONF_HOST]
        self.unique_id = f"{entry.unique_id}_full"
        self._known_sms_signatures: dict[str, set[str]] = {}
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}-{self._host}-full",
            update_interval=timedelta(seconds=update_interval),
        )

    def _message_signature(self, message: dict) -> str:
        return "|".join(
            [
                str(message.get("id", "")),
                str(message.get("timestamp", "")),
                str(message.get("sender", "")),
                str(message.get("text", "")),
            ]
        )

    def _process_new_sms(self, full_data) -> None:
        current_signatures: dict[str, set[str]] = {}

        for interface_id, messages in full_data.show_modem_sms.items():
            current_signatures[interface_id] = {
                self._message_signature(message) for message in messages
            }

        if not self._known_sms_signatures:
            self._known_sms_signatures = current_signatures
            return

        for interface_id, messages in full_data.show_modem_sms.items():
            known = self._known_sms_signatures.get(interface_id, set())
            for message in messages:
                signature = self._message_signature(message)
                if signature in known:
                    continue

                self.hass.bus.async_fire(
                    EVENT_NEW_SMS,
                    {
                        "entry_id": self.entry.entry_id,
                        "router_mac": self.router.mac,
                        "router_name": self.entry.title,
                        "interface": interface_id,
                        "message": message,
                    },
                )
                self._publish_sms_to_mqtt(interface_id, message)
                _LOGGER.debug(
                    "%s new sms on %s: %s",
                    self.router.mac,
                    interface_id,
                    message.get("id"),
                )

        self._known_sms_signatures = current_signatures

    def _publish_sms_to_mqtt(self, interface_id: str, message: dict) -> None:
        if not self.entry.options.get(CONF_MQTT_PUBLISH_SMS, False):
            return

        topic_base = self.entry.options.get(CONF_MQTT_TOPIC_BASE, DEFAULT_MQTT_TOPIC_BASE).strip("/")
        topic = f"{topic_base}/incoming"
        payload = {
            "entry_id": self.entry.entry_id,
            "router_mac": self.router.mac,
            "router_name": self.entry.title,
            "interface": interface_id,
            "message": message,
        }

        mqtt_async_publish(
            self.hass,
            topic,
            json.dumps(payload, ensure_ascii=False),
        )

    async def _async_update_data(self):
        _errr = None
        try:
            full_data = await self.router.custom_request()
        except Exception as err:
            _LOGGER.debug(f"{self.router.mac} UpdateFailed _async_update_data (err {err})")
            _errr = err
        try:
            coordinator_firmware = self.hass.data[DOMAIN][self.entry.entry_id][COORD_FIREWARE]
            if (not coordinator_firmware.last_update_success) or _errr != None:
                await coordinator_firmware.async_refresh()
        except Exception:
                pass
        if _errr != None:
            raise UpdateFailed(f"{self.router.mac} UpdateFailed (err {_errr})")
        self._process_new_sms(full_data)
        return full_data

    @property
    def device_info(self) -> DeviceInfo:
        """Set device info."""
        return DeviceInfo(
            configuration_url=self.router.url_router,
            connections={(CONNECTION_NETWORK_MAC, self.router.mac)},
            identifiers={(DOMAIN, self.router.mac)},
            manufacturer="Keenetic Ltd.",
            name=self.entry.unique_id,
            model=self.router.model,
            hw_version=self.router.hw_version,
            sw_version=f"{self.router.fw_version} ({self.router.fw_branch})",
        )


class KeeneticRouterFirmwareCoordinator(DataUpdateCoordinator):
    def __init__(
            self,
            hass: HomeAssistant,
            router: Router,
            update_interval: int,
            entry: ConfigEntry
    ) -> None:
        self.router = router
        self.entry = entry
        self.unique_id = f"{entry.unique_id}_fw"
        self._host = entry.data[CONF_HOST]
        self._version_firmware = {}
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}-{self._host}-fw",
            update_interval=timedelta(seconds=update_interval),
        )

    async def _async_update_data(self):
        repeat=0
        while repeat < COUNT_REPEATED_REQUEST_FIREWARE:
            repeat += 1
            data_components_list = await self.router.components_list()
            if not data_components_list.get('continued', False):
                break
            _LOGGER.debug(f"{self.router.mac} data_components_list not data {data_components_list}")
            await asyncio.sleep(TIMER_REPEATED_REQUEST_FIREWARE)
        firmware = {}
        firmware['new'] = data_components_list.get('firmware')
        firmware['current'] = data_components_list.get('local')
        firmware['sandbox'] = data_components_list.get('sandbox')
        if (
            self._version_firmware == {} 
            or self._version_firmware.get("new", {}).get("version") != firmware.get("new", {}).get("version") 
            or self._version_firmware.get("current", {}).get("version") != firmware.get("current", {}).get("version")
        ):
            repeat=0
            while repeat < COUNT_REPEATED_REQUEST_FIREWARE:
                repeat += 1
                try:
                    if firmware.get('new') and firmware.get('new', {}).get('version') and firmware.get('sandbox') is not None:
                        data_release_notes = await self.router.release_notes(firmware['new']['version'], FW_SANDBOX[firmware['sandbox']])
                        if not data_release_notes.get('continued', False):
                            break
                        _LOGGER.debug(f"{self.router.mac} data_release_notes not data {data_release_notes}")
                    else:
                        _LOGGER.debug(f"{self.router.mac} Missing required firmware data for release notes")
                        break
                except Exception as err:
                    _LOGGER.debug(f"{self.router.mac} Error getting release notes: {err}")
                    break
                await asyncio.sleep(TIMER_REPEATED_REQUEST_FIREWARE)

            try:
                if isinstance(data_release_notes, dict) and 'webhelp' in data_release_notes:
                    webhelp = data_release_notes['webhelp']
                    if isinstance(webhelp, dict) and 'ru' in webhelp and isinstance(webhelp['ru'], list) and len(webhelp['ru']) > 0:
                        firmware['release_notes'] = webhelp['ru'][0].get('href', '')
                        firmware['channel'] = webhelp['ru'][0].get('title', '')
                    else:
                        firmware['release_notes'] = ''
                        firmware['channel'] = ''
                else:
                    firmware['release_notes'] = ''
                    firmware['channel'] = ''
            except Exception as err:
                _LOGGER.debug(f"{self.router.mac} Error processing release notes: {err}")
                firmware['release_notes'] = ''
                firmware['channel'] = ''
            
            self._version_firmware = firmware
        return self._version_firmware

    @property
    def device_info(self) -> DeviceInfo:
        """Set device info."""
        vfw = self._version_firmware.get("current")
        if vfw != None:
            sw_version = vfw.get("title")
        else:
            sw_version = None
        return DeviceInfo(
            connections={(CONNECTION_NETWORK_MAC, self.router.mac)},
            sw_version=sw_version,
        )


class KeeneticRouterRcInterfaceCoordinator(DataUpdateCoordinator):
    def __init__(
            self,
            hass: HomeAssistant,
            router: Router,
            update_interval: int,
            entry: ConfigEntry
    ) -> None:
        self.router = router
        self.entry = entry
        self._host = entry.data[CONF_HOST]
        self.unique_id = f"{entry.unique_id}_rc_interface"
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}-{self._host}-rc-interface",
            update_interval=timedelta(minutes=update_interval),
        )

    async def _async_update_data(self):
        try:
            return await self.router.show_rc_interface()
        except Exception as err:
            _LOGGER.debug(f"{self.router.mac} UpdateFailed _async_update_data (err {err})")
            raise UpdateFailed(f"{self.router.mac} UpdateFailed {err}")

    @property
    def device_info(self) -> DeviceInfo:
        """Set device info."""
        return DeviceInfo(
            connections={(CONNECTION_NETWORK_MAC, self.router.mac)}
        )
