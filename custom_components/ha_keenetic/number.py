"""The Keenetic API number entities."""

from __future__ import annotations
import logging

from homeassistant.components.number import NumberEntity, NumberMode, NumberDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import EntityCategory, UnitOfTime

from .coordinator import KeeneticRouterRcInterfaceCoordinator
from .const import (
    DOMAIN,
    COORD_RC_INTERFACE,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id][COORD_RC_INTERFACE]
    numbers: list[NumberEntity] = []
    if coordinator != None:
        interfaces = coordinator.data
        for interface in interfaces:
            interface_data = interfaces[interface]
            if (interface.startswith('WifiMaster') and
                ('AccessPoint' not in interface) and
                ('WifiStation' not in interface)):
                    numbers.append(
                        KeeneticClientsIdleTimeoutWifiNumber(
                            coordinator,
                            interface,
                            interface_data.name_interface,
                        )
                    )
    async_add_entities(numbers)


class KeeneticClientsIdleTimeoutWifiNumber(CoordinatorEntity[KeeneticRouterRcInterfaceCoordinator], NumberEntity):

    _attr_entity_registry_enabled_default = False
    _attr_has_entity_name = True
    _attr_translation_key = "clients_idle_timeout_wifi"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_device_class = NumberDeviceClass.DURATION

    def __init__(
        self,
        coordinator: KeeneticRouterRcInterfaceCoordinator,
        interface,
        name_interface,
    ) -> None:
        super().__init__(coordinator)
        self._attr_device_info = coordinator.device_info
        self._attr_mode = NumberMode.BOX
        self._interface = interface
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.unique_id}_{self._attr_translation_key}_{name_interface}"
        self._attr_native_min_value = 60
        self._attr_native_max_value = 2147483646
        self._attr_native_step = 1
        self._attr_translation_placeholders = {"name_interface": name_interface}

    @property
    def native_value(self) -> float | None:
        return float(self.coordinator.data[self._interface].idle_timeout)

    async def async_set_native_value(self, value: int) -> None:
        try:
            resp = await self.coordinator.router.set_clients_idle_timeout_wifi(self._interface, value)
            await self.coordinator.async_request_refresh()
        except Exception as err:
            _LOGGER.error(f"Error setting idle timeout (err {err})")
            raise