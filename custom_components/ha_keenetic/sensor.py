"""The Keenetic API sensor entities."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    PERCENTAGE,
    UnitOfDataRate,
    UnitOfInformation,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .coordinator import KeeneticRouterCoordinator
from .keenetic import KeeneticFullData
from .const import (
    DOMAIN,
    COORD_FULL,
    CONF_SENSOR_GROUPS,
    DEFAULT_SENSOR_GROUPS,
    SENSOR_GROUP_INTERFACE,
    SENSOR_GROUP_MESH,
    SENSOR_GROUP_ROUTER,
    SENSOR_GROUP_STORAGE,
    SENSOR_GROUP_WIFI,
)
from .icons import ICON_MESH_NODE, ICON_MESH_NODE_OFFLINE

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class KeeneticRouterSensorEntityDescription(SensorEntityDescription):
    """A class that describes sensor entities."""
    value: Callable[[KeeneticFullData, Any], Any] = (
        lambda coordinator, key: coordinator.data.show_system[key] if coordinator.data.show_system[key] is not None else None
    )
    attributes_fn: Callable[[KeeneticFullData], dict[str, Any]] | None = None


@dataclass(frozen=True, kw_only=True)
class KeeneticInterfaceSensorEntityDescription(SensorEntityDescription):
    """A class that describes interface statistic sensor entities."""

    value: Callable[[KeeneticFullData, str], StateType]


@dataclass(frozen=True, kw_only=True)
class KeeneticStorageSensorEntityDescription(SensorEntityDescription):
    """A class that describes storage partition sensor entities."""

    value: Callable[[dict[str, Any]], StateType]


def convert_uptime(uptime: int) -> datetime:
    """Convert uptime."""
    if uptime != None:
        return (datetime.now(tz=UTC) - timedelta(seconds=int(uptime))).replace(second=0, microsecond=0)
    else:
        return None

def convert_data_size(data_size: int = 0) -> float:
    """Convert data_size."""
    return round(data_size/1024/1024, 3)

def ind_wan_ip_adress(fdata: KeeneticFullData):
    """Определение внешнего IP адреса."""
    try:
        data_p_i = fdata.priority_interface
        show_interface = fdata.show_interface
        priority_interface = sorted(data_p_i, key=lambda x: data_p_i[x]['order'])
        for row in priority_interface:
            if show_interface[row]["connected"] == "yes":
                if row.startswith('Wireguard'):
                    return show_interface[row]["wireguard"]["peer"][0]["remote"]
                else:
                    return show_interface[row]["address"]
    except Exception as ex:
        _LOGGER.debug(f'Not ind_wan_ip_adress - {ex}')
        return None


SENSOR_TYPES: tuple[KeeneticRouterSensorEntityDescription, ...] = (
    KeeneticRouterSensorEntityDescription(
        key="cpuload",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=PERCENTAGE,
    ),
    KeeneticRouterSensorEntityDescription(
        key="memory",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=PERCENTAGE,
        value=lambda coordinator, key: int(float(coordinator.data.show_system[key].split('/')[0])/float(coordinator.data.show_system[key].split('/')[1])*100),
    ),
    KeeneticRouterSensorEntityDescription(
        key="uptime",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda coordinator, key: convert_uptime(coordinator.data.show_system[key]),
    ),
    KeeneticRouterSensorEntityDescription(
        key="wan_ip_adress",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda coordinator, key: ind_wan_ip_adress(coordinator.data),
    ),
    KeeneticRouterSensorEntityDescription(
        key="clients_wifi",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda coordinator, key: len(coordinator.data.show_associations.get("station", [])),
    ),
    KeeneticRouterSensorEntityDescription(
        key="hostname",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda coordinator, key: coordinator.data.show_system.get("hostname", ""),
    ),
    KeeneticRouterSensorEntityDescription(
        key="domainname",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda coordinator, key: coordinator.data.show_system.get("domainname", ""),
    ),
)

INTERFACE_SENSOR_TYPES: tuple[KeeneticInterfaceSensorEntityDescription, ...] = (
    KeeneticInterfaceSensorEntityDescription(
        key="rxspeed",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        value=lambda data, interface_id: data.stat_interface.get(interface_id, {}).get("rxspeed"),
    ),
    KeeneticInterfaceSensorEntityDescription(
        key="txspeed",
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        value=lambda data, interface_id: data.stat_interface.get(interface_id, {}).get("txspeed"),
    ),
    KeeneticInterfaceSensorEntityDescription(
        key="rxbytes",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        value=lambda data, interface_id: data.stat_interface.get(interface_id, {}).get("rxbytes"),
    ),
    KeeneticInterfaceSensorEntityDescription(
        key="txbytes",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        value=lambda data, interface_id: data.stat_interface.get(interface_id, {}).get("txbytes"),
    ),
)

WIFI_RADIO_SENSOR_TYPES: tuple[KeeneticInterfaceSensorEntityDescription, ...] = (
    KeeneticInterfaceSensorEntityDescription(
        key="wifi_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="°C",
        value=lambda data, interface_id: data.show_interface.get(interface_id, {}).get("temperature"),
    ),
    KeeneticInterfaceSensorEntityDescription(
        key="wifi_channel",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda data, interface_id: int(data.show_interface.get(interface_id, {}).get("channel"))
        if data.show_interface.get(interface_id, {}).get("channel") is not None
        else None,
    ),
    KeeneticInterfaceSensorEntityDescription(
        key="wifi_bandwidth",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="MHz",
        value=lambda data, interface_id: int(data.show_interface.get(interface_id, {}).get("bandwidth"))
        if data.show_interface.get(interface_id, {}).get("bandwidth") is not None
        else None,
    ),
    KeeneticInterfaceSensorEntityDescription(
        key="wifi_bitrate",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="bit/s",
        value=lambda data, interface_id: data.show_interface.get(interface_id, {}).get("bitrate"),
    ),
)

STORAGE_SENSOR_TYPES: tuple[KeeneticStorageSensorEntityDescription, ...] = (
    KeeneticStorageSensorEntityDescription(
        key="storage_total",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        value=lambda partition: int(partition["total"]) if partition.get("total") is not None else None,
    ),
    KeeneticStorageSensorEntityDescription(
        key="storage_free",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        value=lambda partition: int(partition["free"]) if partition.get("free") is not None else None,
    ),
    KeeneticStorageSensorEntityDescription(
        key="storage_used",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        value=lambda partition: (
            int(partition["total"]) - int(partition["free"])
            if partition.get("total") is not None and partition.get("free") is not None
            else None
        ),
    ),
    KeeneticStorageSensorEntityDescription(
        key="storage_used_percent",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=PERCENTAGE,
        value=lambda partition: (
            round((int(partition["total"]) - int(partition["free"])) / int(partition["total"]) * 100, 1)
            if partition.get("total") and partition.get("free") is not None
            else None
        ),
    ),
    KeeneticStorageSensorEntityDescription(
        key="storage_state",
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda partition: partition.get("state"),
    ),
)


def iter_storage_partitions(show_media: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """Return flattened media partition rows."""
    partitions = []
    if not isinstance(show_media, dict):
        return partitions

    for media_id, media_data in show_media.items():
        if not isinstance(media_data, dict):
            continue

        raw_partitions = media_data.get("partition", [])
        if isinstance(raw_partitions, dict):
            raw_partitions = raw_partitions.values()
        elif not isinstance(raw_partitions, list):
            raw_partitions = [raw_partitions]

        for partition in raw_partitions:
            if not isinstance(partition, dict):
                continue
            partition_id = partition.get("id") or partition.get("label") or media_id
            partitions.append((media_id, partition_id, partition))
    return partitions


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Keenetic sensor."""
    coordinator = hass.data[DOMAIN][entry.entry_id][COORD_FULL]
    sensors = []
    sensor_groups = set(entry.options.get(CONF_SENSOR_GROUPS, DEFAULT_SENSOR_GROUPS))
    
    if SENSOR_GROUP_ROUTER in sensor_groups:
        for description in SENSOR_TYPES:
            try:
                if description.value(coordinator, description.key) is not None:
                    sensors.append(KeeneticRouterSensor(coordinator, description, description.key, description.key))
            except Exception as err:
                _LOGGER.debug(f'async_setup_entry sensor SENSOR_TYPES {description} err - {err}')

    if SENSOR_GROUP_INTERFACE in sensor_groups:
        for interface_id in coordinator.router.request_interface:
            for description in INTERFACE_SENSOR_TYPES:
                try:
                    if description.value(coordinator.data, interface_id) is not None:
                        sensors.append(
                            KeeneticInterfaceStatSensor(
                                coordinator,
                                description,
                                interface_id,
                            )
                        )
                except Exception as err:
                    _LOGGER.debug("Interface sensor setup skipped for %s %s: %s", interface_id, description.key, err)

    if SENSOR_GROUP_WIFI in sensor_groups:
        for interface_id, interface_data in coordinator.data.show_interface.items():
            if not interface_id.startswith("WifiMaster"):
                continue

            for description in WIFI_RADIO_SENSOR_TYPES:
                try:
                    if description.value(coordinator.data, interface_id) is not None:
                        sensors.append(
                            KeeneticWifiRadioSensor(
                                coordinator,
                                description,
                                interface_id,
                                interface_data,
                            )
                        )
                except Exception as err:
                    _LOGGER.debug("Wi-Fi radio sensor setup skipped for %s %s: %s", interface_id, description.key, err)

    if SENSOR_GROUP_STORAGE in sensor_groups:
        for media_id, partition_id, partition_data in iter_storage_partitions(coordinator.data.show_media):
            for description in STORAGE_SENSOR_TYPES:
                try:
                    if description.value(partition_data) is not None:
                        sensors.append(
                            KeeneticStorageSensor(
                                coordinator,
                                description,
                                media_id,
                                partition_id,
                                partition_data,
                            )
                        )
                except Exception as err:
                    _LOGGER.debug("Storage sensor setup skipped for %s %s %s: %s", media_id, partition_id, description.key, err)

    if coordinator.router.hw_type == "router" and SENSOR_GROUP_MESH in sensor_groups:
        try:
            _LOGGER.debug("Attempting to get mesh nodes")
            mesh_nodes = await coordinator.router.get_mesh_nodes()
            _LOGGER.debug("Got mesh nodes: %s", mesh_nodes)
            
            if mesh_nodes:
                for node_id, node_data in mesh_nodes.items():
                    _LOGGER.debug("Creating sensor for mesh node: %s", node_id)
                    sensors.append(
                        KeeneticMeshNodeSensor(
                            coordinator,
                            node_id,
                            node_data,
                        )
                    )
                _LOGGER.debug("Created %d mesh node sensors", len(mesh_nodes))
            else:
                _LOGGER.debug("No mesh nodes found")
        except Exception as ex:
            _LOGGER.error(f"Error setting up mesh node sensors: {ex}", exc_info=True)
    
    async_add_entities(sensors, False)

class KeeneticMeshNodeSensor(CoordinatorEntity[KeeneticRouterCoordinator], SensorEntity):
    """Representation of a Keenetic Mesh Node sensor."""
    
    _attr_has_entity_name = True
    MESH_NODE_PREFIX = "mesh_node_"
    
    def __init__(
        self,
        coordinator: KeeneticRouterCoordinator,
        node_id: str,
        node_data: dict,
    ) -> None:
        """Initialize the mesh node sensor."""
        super().__init__(coordinator)
        self._node_id = node_id
        self._node_data = node_data
        
        model = node_data.get("model", "")
        known_host = node_data.get("known-host", "") or node_data.get("known_host", "")
        if known_host:
            display_name = f"{model}"
        else:
            display_name = f"Node {node_id}"
        
        self._attr_name = f"Mesh {display_name}"
        self._attr_translation_key = None
        self._attr_translation_placeholders = None
        
        self._attr_unique_id = f"{coordinator.unique_id}_{self.MESH_NODE_PREFIX}{node_id}"

        self.entity_id = f"sensor.keenetic_{self.MESH_NODE_PREFIX}{node_id.replace(':', '_')}"
        
        self._attr_device_info = coordinator.device_info
    
    @property
    def icon(self) -> str:
        """Return the icon of the sensor."""
        return ICON_MESH_NODE if self._node_data.get("status") == "connected" else ICON_MESH_NODE_OFFLINE
    
    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self._node_data.get("status", "unknown")
    
    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attributes = self._node_data.get("attributes", {})
        
        result = {
            "ip_address": attributes.get("ip", ""),
            "mode": attributes.get("mode", ""),
            "hw_id": attributes.get("hw_id", ""),
            "firmware": attributes.get("firmware", ""),
            "firmware_available": attributes.get("firmware_available", ""),
            "memory": attributes.get("memory", ""),
            "uptime": attributes.get("uptime", ""),
            "cloud_state": attributes.get("cloud_agent_state", ""),
            "internet_available": attributes.get("internet_available", False),
        }
        
        return result

class KeeneticRouterSensor(CoordinatorEntity[KeeneticRouterCoordinator], SensorEntity):
    _attr_has_entity_name = True
    entity_description: KeeneticRouterSensorEntityDescription

    def __init__(
            self,
            coordinator: KeeneticRouterCoordinator,
            description: KeeneticRouterSensorEntityDescription,
            obj_id: str,
            obj_name: str,
    ) -> None:
        super().__init__(coordinator)

        self._attr_device_info = coordinator.device_info
        self.obj_id = obj_id
        self._attr_unique_id = f"{coordinator.router.mac}_{description.key}"
        if obj_id != description.key:
            self._attr_unique_id += f"_{obj_id}"
            
        self.entity_description = description
        self._attr_translation_key = description.key
        self._attr_translation_placeholders = {"name": f"{obj_name}"}
        
        device_name = slugify(coordinator.router.model)
        self.entity_id = f"sensor.{device_name}_{description.key}"
        if obj_id != description.key:
            self.entity_id += f"_{obj_id}"

    @property
    def native_value(self) -> StateType:
        """Sensor value."""
        return self.entity_description.value(self.coordinator, self.obj_id)

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Return the state attributes of the sensor."""
        if self.entity_description.attributes_fn is not None:
            return self.entity_description.attributes_fn(self.coordinator.data)
        else:
            return None


class KeeneticInterfaceStatSensor(CoordinatorEntity[KeeneticRouterCoordinator], SensorEntity):
    """Representation of a Keenetic interface statistic sensor."""

    _attr_has_entity_name = True
    entity_description: KeeneticInterfaceSensorEntityDescription

    def __init__(
        self,
        coordinator: KeeneticRouterCoordinator,
        description: KeeneticInterfaceSensorEntityDescription,
        interface_id: str,
    ) -> None:
        """Initialize the interface statistic sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._interface_id = interface_id
        self._interface_name = coordinator.router.request_interface.get(interface_id, interface_id)
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.router.mac}_{interface_id}_{description.key}"
        self._attr_translation_key = description.key
        self._attr_translation_placeholders = {"name": self._interface_name}

    @property
    def native_value(self) -> StateType:
        """Return interface statistic value."""
        return self.entity_description.value(self.coordinator.data, self._interface_id)

    @property
    def extra_state_attributes(self) -> dict[str, StateType]:
        """Return normalized interface attributes."""
        interface_data = self.coordinator.data.show_interface.get(self._interface_id, {})
        return {
            "interface_id": self._interface_id,
            "interface_name": self._interface_name,
            "interface_type": interface_data.get("type"),
            "description": interface_data.get("description"),
            "state": interface_data.get("state"),
            "link": interface_data.get("link"),
            "connected": interface_data.get("connected"),
            "ip_address": interface_data.get("address"),
        }


class KeeneticWifiRadioSensor(CoordinatorEntity[KeeneticRouterCoordinator], SensorEntity):
    """Representation of a Keenetic Wi-Fi radio diagnostic sensor."""

    _attr_has_entity_name = True
    entity_description: KeeneticInterfaceSensorEntityDescription

    def __init__(
        self,
        coordinator: KeeneticRouterCoordinator,
        description: KeeneticInterfaceSensorEntityDescription,
        interface_id: str,
        interface_data: dict[str, Any],
    ) -> None:
        """Initialize the Wi-Fi radio sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._interface_id = interface_id
        self._interface_name = interface_data.get("description") or interface_id
        self._attr_device_info = coordinator.device_info
        self._attr_unique_id = f"{coordinator.router.mac}_{interface_id}_{description.key}"
        self._attr_translation_key = description.key
        self._attr_translation_placeholders = {"name": self._interface_name}

    @property
    def native_value(self) -> StateType:
        """Return Wi-Fi radio diagnostic value."""
        return self.entity_description.value(self.coordinator.data, self._interface_id)

    @property
    def extra_state_attributes(self) -> dict[str, StateType]:
        """Return normalized Wi-Fi radio attributes."""
        interface_data = self.coordinator.data.show_interface.get(self._interface_id, {})
        return {
            "interface_id": self._interface_id,
            "interface_name": self._interface_name,
            "state": interface_data.get("state"),
            "link": interface_data.get("link"),
            "connected": interface_data.get("connected"),
            "channel": interface_data.get("channel"),
            "bandwidth": interface_data.get("bandwidth"),
            "bitrate": interface_data.get("bitrate"),
            "temperature": interface_data.get("temperature"),
        }


class KeeneticStorageSensor(CoordinatorEntity[KeeneticRouterCoordinator], SensorEntity):
    """Representation of a Keenetic storage partition sensor."""

    _attr_has_entity_name = True
    entity_description: KeeneticStorageSensorEntityDescription

    def __init__(
        self,
        coordinator: KeeneticRouterCoordinator,
        description: KeeneticStorageSensorEntityDescription,
        media_id: str,
        partition_id: str,
        partition_data: dict[str, Any],
    ) -> None:
        """Initialize the storage sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._media_id = media_id
        self._partition_id = partition_id
        self._partition_name = partition_data.get("label") or partition_id
        self._attr_device_info = coordinator.device_info
        storage_slug = slugify(f"{media_id}_{partition_id}")
        self._attr_unique_id = f"{coordinator.router.mac}_{storage_slug}_{description.key}"
        self._attr_translation_key = description.key
        self._attr_translation_placeholders = {"name": self._partition_name}

    @property
    def native_value(self) -> StateType:
        """Return storage partition diagnostic value."""
        partition_data = self._partition_data
        return self.entity_description.value(partition_data)

    @property
    def _partition_data(self) -> dict[str, Any]:
        """Return the latest storage partition data."""
        for media_id, partition_id, partition_data in iter_storage_partitions(self.coordinator.data.show_media):
            if media_id == self._media_id and partition_id == self._partition_id:
                return partition_data
        return {}

    @property
    def extra_state_attributes(self) -> dict[str, StateType]:
        """Return normalized storage attributes."""
        media_data = self.coordinator.data.show_media.get(self._media_id, {})
        partition_data = self._partition_data
        return {
            "media_id": self._media_id,
            "partition_id": self._partition_id,
            "label": partition_data.get("label"),
            "filesystem": partition_data.get("fstype"),
            "state": partition_data.get("state"),
            "used_by": partition_data.get("used-by"),
            "removable": media_data.get("removable"),
            "ejectable": media_data.get("ejectable"),
        }
