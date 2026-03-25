import logging
from collections.abc import Mapping
from typing import Any

from homeassistant.helpers import device_registry as dr
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError

from .const import (
    DOMAIN,
    CROUTER,
)

_LOGGER = logging.getLogger(__name__)

SUPPORTED_SERVICES = [
    "request_api",
    "backup_router",
    "read_sms",
    "send_sms",
    "read_sms_item",
    "delete_sms",
]


def _get_sms_interface(router, data: Mapping[str, Any]) -> str:
    interface = data.get("interface") or router.get_default_sms_interface()
    if not interface:
        raise ServiceValidationError(
            "Не указан SMS интерфейс модема. Задайте interface в сервисе или в настройках интеграции.",
            DOMAIN,
        )
    return interface


async def async_setup_services(hass: HomeAssistant) -> None:

    services = {
        "request_api": request_api,
        "backup_router": backup_router,
        "read_sms": read_sms,
        "send_sms": send_sms,
        "read_sms_item": read_sms_item,
        "delete_sms": delete_sms,
    }

    async def async_call_keenetic_service(service_call: ServiceCall) -> None:
        if entry_id := service_call.data.get('entry_id', False):
            current_entry_id = entry_id
        elif device_id := service_call.data.get('device_id', False):
            device_registry = dr.async_get(hass)
            if (device_entry := device_registry.async_get(device_id)) is None:
                raise ServiceValidationError(f"Некорректный device ID: {device_id}.", DOMAIN)
            for entry_id in device_entry.config_entries:
                if (entry := hass.config_entries.async_get_entry(entry_id)) is None:
                    continue
                if entry.domain == DOMAIN:
                    current_entry_id = entry_id
                    break
        else:
            raise ServiceValidationError("Нет параметра entry_id или device_id.", DOMAIN)
        return await services[service_call.service](hass, current_entry_id, service_call.data)

    for service in SUPPORTED_SERVICES:
        hass.services.async_register(
            DOMAIN,
            service,
            async_call_keenetic_service,
            supports_response=SupportsResponse.OPTIONAL,
        )


@callback
def async_unload_services(hass: HomeAssistant) -> None:
    for service in SUPPORTED_SERVICES:
        hass.services.async_remove(DOMAIN, service)


async def request_api(hass: HomeAssistant, entry_id: str, data: Mapping[str, Any]):
    data_json = data.get("data_json", [])
    response = await hass.data[DOMAIN][entry_id][CROUTER].api(data["method"], data["endpoint"], data_json)
    _LOGGER.debug(f'Services request_api response - {response}')
    return {"response": response}


async def backup_router(hass: HomeAssistant, entry_id: str, data: Mapping[str, Any]):
    response = await hass.data[DOMAIN][entry_id][CROUTER].async_backup(data["folder"], data["type"])
    return {"response": "success"}


async def read_sms(hass: HomeAssistant, entry_id: str, data: Mapping[str, Any]):
    router = hass.data[DOMAIN][entry_id][CROUTER]
    interface = data.get("interface") or router.get_default_sms_interface()
    folder = data.get("folder", "inbox")

    if interface:
        sms_data = await router.get_modem_sms_details(interface, folder)
        return {
            "interface": interface,
            "folder": folder,
            "messages": sms_data["messages"],
            "stats": sms_data.get("stats", {}),
            "transport": sms_data.get("transport"),
            "command": sms_data.get("command"),
        }

    messages = await router.get_all_modem_sms()
    return {"messages": messages}


async def send_sms(hass: HomeAssistant, entry_id: str, data: Mapping[str, Any]):
    router = hass.data[DOMAIN][entry_id][CROUTER]
    interface = _get_sms_interface(router, data)
    response = await router.send_modem_sms(interface, data["phone"], data["text"])
    return {"response": response}


async def read_sms_item(hass: HomeAssistant, entry_id: str, data: Mapping[str, Any]):
    router = hass.data[DOMAIN][entry_id][CROUTER]
    interface = _get_sms_interface(router, data)
    response = await router.read_modem_sms(interface, data["sms_id"])
    return {"message": response}


async def delete_sms(hass: HomeAssistant, entry_id: str, data: Mapping[str, Any]):
    router = hass.data[DOMAIN][entry_id][CROUTER]
    interface = _get_sms_interface(router, data)
    response = await router.delete_modem_sms(interface, data["sms_id"])
    return {"response": response}
