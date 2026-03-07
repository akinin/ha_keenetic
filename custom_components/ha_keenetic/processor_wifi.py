"""WiFi data processor for Keenetic integration."""
import logging
from typing import Dict, Any, Callable, List, Union

_LOGGER = logging.getLogger(__name__)

class WiFiProcessor:
    
    @staticmethod
    async def process_wifi_interfaces(
            interface_info: dict, 
            rc_interface_info: dict,
            get_associations_fn: Callable
        ) -> Dict[str, Any]:
        wifi_data = {}
        try:
            associations = await get_associations_fn()
            
            for interface_id, interface_data in interface_info.items():
                if interface_id.startswith('WifiMaster') or '/AccessPoint' in interface_id:
                    rc_data = rc_interface_info.get(interface_id, None)
                    
                    if '/AccessPoint' in interface_id:
                        interface_type = "AccessPoint"
                        master_id = interface_id.split('/')[0]
                    else:
                        interface_type = "WifiMaster"
                        master_id = interface_id
                    
                    wifi_password = ""
                    if rc_data:
                        wifi_password = rc_data.password
                    
                    band = "5GHz" if "WifiMaster1" in interface_id else "2.4GHz"
                    ssid = interface_data.get('ssid', '')
                    if not ssid and rc_data:
                        ssid = rc_data.ssid
                    state = interface_data.get('state', 'down')
                    link = interface_data.get('link', 'down')
                    is_up = interface_data.get('up', False)
                    encryption = interface_data.get('encryption', {})
                    connected_clients = 0
                    connected = "no"

                    if isinstance(associations, dict):
                        for client in associations.values():
                            if isinstance(client, dict) and client.get('interface', {}).get('id') == interface_id:
                                connected_clients += 1
                                connected = "yes"
                    elif isinstance(associations, list):
                        for client in associations:
                            if isinstance(client, dict) and client.get('interface', {}).get('id') == interface_id:
                                connected_clients += 1
                                connected = "yes"

                    wifi_data[interface_id] = {
                        "id": interface_id,
                        "type": interface_type,
                        "master": master_id,
                        "band": band,
                        "description": interface_data.get("description", ""),
                        "ssid": ssid,
                        "up": is_up,
                        "link": link,
                        "state": state,
                        "mac": interface_data.get("mac", ""),
                        "interface-name": interface_data.get("interface-name", ""),
                        "connected": connected,
                        "connected_clients": connected_clients,
                        "password": wifi_password,
                        "encryption": encryption,
                        "attributes": {
                            "band": band,
                            "ssid": ssid,
                            "description": interface_data.get("description", ""),
                            "connected_clients": connected_clients,
                            "encryption": encryption,
                            "interface-name": interface_data.get("interface-name", ""),
                            "connected": connected,
                            "password": wifi_password
                        }
                    }

                    for key, value in interface_data.items():
                        if key not in ["id", "type", "description", "ssid", "up", "link", "mac", "interface-name", "state", "encryption"]:
                            wifi_data[interface_id][key] = value
                            if key not in wifi_data[interface_id]["attributes"]:
                                wifi_data[interface_id]["attributes"][key] = value
            
            _LOGGER.debug("Processed WiFi interfaces: %s", wifi_data)
            return wifi_data
        except Exception as ex:
            _LOGGER.error("Error processing WiFi interfaces: %s", str(ex))
            return {}