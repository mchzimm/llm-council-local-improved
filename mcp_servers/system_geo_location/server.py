#!/usr/bin/env python3
"""System Geo-Location MCP server for retrieving location based on IP."""

import json
import urllib.request
import urllib.error
from typing import Dict, Any


def get_system_geo_location() -> Dict[str, Any]:
    """Get the system's geographic location based on IP using ipinfo.io.
    
    Returns:
        Dictionary with success status and location data or error
    """
    try:
        # Use ipinfo.io API - free tier, no auth required for basic info
        req = urllib.request.Request(
            "https://ipinfo.io/json",
            headers={'User-Agent': 'Mozilla/5.0 (compatible; LLMCouncil/1.0)'}
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        # Extract location fields
        location = {
            'city': data.get('city', ''),
            'state': data.get('region', ''),
            'postal': data.get('postal', ''),
            'country': data.get('country', ''),
            'ip': data.get('ip', ''),
            'timezone': data.get('timezone', ''),
            'coordinates': data.get('loc', '')
        }
        
        # Format the result
        result_parts = []
        if location.get('city'):
            result_parts.append(f"City: {location['city']}")
        if location.get('state'):
            result_parts.append(f"State/Region: {location['state']}")
        if location.get('postal'):
            result_parts.append(f"Postal Code: {location['postal']}")
        if location.get('country'):
            result_parts.append(f"Country: {location['country']}")
        if location.get('ip'):
            result_parts.append(f"IP Address: {location['ip']}")
        if location.get('timezone'):
            result_parts.append(f"Timezone: {location['timezone']}")
        if location.get('coordinates'):
            result_parts.append(f"Coordinates: {location['coordinates']}")
        
        return {
            "success": True,
            "location": "\n".join(result_parts),
            "data": location
        }
        
    except urllib.error.URLError as e:
        return {
            "success": False,
            "error": f"Network error: {str(e)}"
        }
    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"Failed to parse response: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# Tool definitions
TOOLS = [
    {
        "name": "get-system-geo-location",
        "description": "Returns the system's geographic location (City, State/Region, Postal Code, Country) based on IP address",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]


def handle_request(request: Dict[str, Any]) -> Dict[str, Any]:
    """Handle a JSON-RPC request."""
    method = request.get("method")
    params = request.get("params", {})
    request_id = request.get("id")
    
    response = {"jsonrpc": "2.0", "id": request_id}
    
    try:
        if method == "initialize":
            response["result"] = {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "system-geo-location",
                    "version": "1.0.0"
                }
            }
        
        elif method == "notifications/initialized":
            return None
        
        elif method == "tools/list":
            response["result"] = {"tools": TOOLS}
        
        elif method == "tools/call":
            tool_name = params.get("name")
            
            if tool_name == "get-system-geo-location":
                result = get_system_geo_location()
            else:
                response["error"] = {
                    "code": -32601,
                    "message": f"Unknown tool: {tool_name}"
                }
                return response
            
            response["result"] = {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, indent=2)
                    }
                ]
            }
        
        else:
            response["error"] = {
                "code": -32601,
                "message": f"Unknown method: {method}"
            }
    
    except Exception as e:
        response["error"] = {
            "code": -32000,
            "message": str(e)
        }
    
    return response


def main():
    """Main entry point for the MCP server."""
    from mcp_servers.http_wrapper import stdio_main
    stdio_main(handle_request, "System Geo-Location MCP")


if __name__ == "__main__":
    main()
