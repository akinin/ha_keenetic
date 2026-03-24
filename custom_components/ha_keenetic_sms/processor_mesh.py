"""Mesh network data processor for Keenetic integration."""
import logging
from typing import Dict, Any, List, Union

_LOGGER = logging.getLogger(__name__)

class MeshProcessor:
    
    @staticmethod
    def process_mesh_nodes(mesh_info: Union[List[Dict[str, Any]], Dict[str, Any], None]) -> Dict[str, Any]:
        processed_mesh = {}
        try:
            _LOGGER.debug("Processing mesh info: %s (type: %s)", mesh_info, type(mesh_info))
            
            nodes_list = []
            if isinstance(mesh_info, dict):
                if "member" in mesh_info:
                    members = mesh_info.get("member", [])
                    if isinstance(members, list):
                        nodes_list = members
                    elif isinstance(members, dict):
                        nodes_list = [members]
                elif "node" in mesh_info:
                    nodes = mesh_info.get("node", [])
                    if isinstance(nodes, list):
                        nodes_list = nodes
                    elif isinstance(nodes, dict):
                        nodes_list = [nodes]
                else:
                    nodes_list = [mesh_info]
            elif isinstance(mesh_info, list):
                nodes_list = mesh_info
            
            _LOGGER.debug("Nodes list for processing: %s", nodes_list)
            
            for node in nodes_list:
                node_id = node.get("mac", "")
                if node_id:
                    system_info = node.get("system", {}) or {}
                    ports_info = node.get("port", []) or []
                    capabilities = node.get("capabilities", {}) or {}
                    model = node.get("model", "")
                    if not model and "device" in node:
                        device_info = node.get("device", {})
                        if isinstance(device_info, dict):
                            model = device_info.get("model", "")

                    hostname = node.get("hostname", "")
                    known_host = node.get("known-host", "")
                    
                    processed_mesh[node_id] = {
                        "id": node_id,
                        "known-host": known_host,
                        "hostname": hostname,
                        "model": model,
                        "status": "connected",
                        "attributes": {
                            "ip": node.get("ip", ""),
                            "mode": node.get("mode", ""),
                            "hw_id": node.get("hw_id", ""),
                            "firmware": node.get("fw", ""),
                            "firmware_available": node.get("fw-available", ""),
                            "memory": system_info.get("memory", ""),
                            "uptime": system_info.get("uptime", ""),
                            "ports": ports_info,
                            "capabilities": capabilities,
                            "cloud_agent_state": node.get("cloud-agent-state", ""),
                            "internet_available": node.get("internet-available", False),
                        }
                    }

                    for key, value in node.items():
                        if key not in ["mac", "known-host", "hostname", "model", "ip", "mode", "hw_id", 
                                      "fw", "fw-available", "system", "port", "capabilities", 
                                      "cloud-agent-state", "internet-available", "device"]:
                            processed_mesh[node_id]["attributes"][key] = value
            
            _LOGGER.debug("Processed mesh nodes: %s", processed_mesh)
            return processed_mesh
        except Exception as ex:
            _LOGGER.error("Error processing mesh nodes: %s", str(ex), exc_info=True)
            return {}