#!/usr/bin/env python3
"""
Location and Time MCP server for comprehensive location/time operations.

Tools:
- get-coordinates-for-location: Get lon/lat for a location name
- get-timezone-for-location: Get timezone for a location name
- get-current-time-for-location: Get current local time for a location
- get-weather-for-location-and-date: Get weather for location name and date
- convert-datetime-between-timezones: Convert datetime between timezones
- calculate-datetime-offset: Add/subtract time from a datetime
- get-daylight-savings-info: Get DST info for location and date
"""

import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
import re


def geocode_location(location_name: str) -> Dict[str, Any]:
    """
    Get coordinates for a location name using Nominatim (OpenStreetMap).
    
    Args:
        location_name: City, address, or place name (e.g., "Seattle, WA" or "Tokyo, Japan")
    
    Returns:
        Dict with lat, lon, display_name, and timezone info
    """
    try:
        # URL encode the location
        encoded_location = urllib.parse.quote(location_name)
        url = f"https://nominatim.openstreetmap.org/search?q={encoded_location}&format=json&limit=1"
        
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'LLMCouncilApp/1.0 (https://github.com/mchzimm/llm-council)'}
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        if not data:
            return {"success": False, "error": f"Could not find location: {location_name}"}
        
        result = data[0]
        lat = float(result['lat'])
        lon = float(result['lon'])
        
        return {
            "success": True,
            "latitude": lat,
            "longitude": lon,
            "display_name": result.get('display_name', location_name),
            "location_query": location_name
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_timezone_for_coordinates(lat: float, lon: float) -> Dict[str, Any]:
    """Get timezone for coordinates using timeapi.io."""
    try:
        url = f"https://timeapi.io/api/TimeZone/coordinate?latitude={lat}&longitude={lon}"
        
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'LLMCouncil/1.0'}
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        return {
            "success": True,
            "timezone": data.get('timeZone', ''),
            "current_local_time": data.get('currentLocalTime', ''),
            "utc_offset": data.get('currentUtcOffset', {}).get('seconds', 0) // 3600,
            "is_dst": data.get('hasDayLightSaving', False) and data.get('isDayLightSavingActive', False)
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_current_time_for_location(location_name: str) -> Dict[str, Any]:
    """Get current local time for a location specified by name."""
    # First geocode the location
    geo = geocode_location(location_name)
    if not geo.get('success'):
        return geo
    
    # Get timezone and current time
    tz_info = get_timezone_for_coordinates(geo['latitude'], geo['longitude'])
    if not tz_info.get('success'):
        return tz_info
    
    return {
        "success": True,
        "location": geo['display_name'],
        "coordinates": {"lat": geo['latitude'], "lon": geo['longitude']},
        "timezone": tz_info['timezone'],
        "current_local_time": tz_info['current_local_time'],
        "utc_offset_hours": tz_info['utc_offset'],
        "is_dst": tz_info['is_dst']
    }


def get_coordinates_for_location(location_name: str) -> Dict[str, Any]:
    """Get longitude and latitude for a location specified by name."""
    geo = geocode_location(location_name)
    if not geo.get('success'):
        return geo
    
    return {
        "success": True,
        "location": geo['display_name'],
        "latitude": geo['latitude'],
        "longitude": geo['longitude'],
        "formatted": f"{geo['latitude']:.6f}, {geo['longitude']:.6f}"
    }


def get_timezone_for_location(location_name: str) -> Dict[str, Any]:
    """Get timezone for a location specified by name."""
    geo = geocode_location(location_name)
    if not geo.get('success'):
        return geo
    
    tz_info = get_timezone_for_coordinates(geo['latitude'], geo['longitude'])
    if not tz_info.get('success'):
        return tz_info
    
    return {
        "success": True,
        "location": geo['display_name'],
        "timezone": tz_info['timezone'],
        "utc_offset_hours": tz_info['utc_offset'],
        "is_dst": tz_info['is_dst']
    }


def get_weather_for_location_and_date(
    location_name: str,
    date: str,
    hour: Optional[int] = None
) -> Dict[str, Any]:
    """
    Get weather for a location name and specific date.
    
    Args:
        location_name: City, address, or place name
        date: Date in YYYY-MM-DD format
        hour: Optional hour (0-23) for specific time
    """
    # Geocode the location
    geo = geocode_location(location_name)
    if not geo.get('success'):
        return geo
    
    lat, lon = geo['latitude'], geo['longitude']
    
    # Validate date
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return {"success": False, "error": f"Invalid date format. Use YYYY-MM-DD (got: {date})"}
    
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    days_diff = (target_date - today).days
    is_historical = days_diff < 0
    is_today = days_diff == 0
    
    try:
        if is_today:
            # For today, include current conditions
            url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={lat}&longitude={lon}"
                f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m"
                f"&hourly=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
                f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code"
                f"&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch"
                f"&timezone=auto"
            )
        elif is_historical:
            # Historical API
            url = (
                f"https://archive-api.open-meteo.com/v1/archive?"
                f"latitude={lat}&longitude={lon}"
                f"&start_date={date}&end_date={date}"
                f"&hourly=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
                f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code"
                f"&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch"
                f"&timezone=auto"
            )
        else:
            if days_diff > 16:
                return {"success": False, "error": f"Forecast only available up to 16 days ahead"}
            
            url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={lat}&longitude={lon}"
                f"&start_date={date}&end_date={date}"
                f"&hourly=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
                f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code"
                f"&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch"
                f"&timezone=auto"
            )
        
        req = urllib.request.Request(url, headers={'User-Agent': 'LLMCouncil/1.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        current = data.get('current', {})
        daily = data.get('daily', {})
        hourly = data.get('hourly', {})
        
        # Weather codes
        weather_codes = {
            0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
            45: "Foggy", 48: "Rime fog", 51: "Light drizzle", 53: "Moderate drizzle",
            55: "Dense drizzle", 61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
            71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow", 95: "Thunderstorm"
        }
        
        result = {
            "success": True,
            "location": geo['display_name'],
            "coordinates": {"lat": lat, "lon": lon},
            "date": date,
            "data_type": "current" if is_today else ("historical" if is_historical else "forecast")
        }
        
        # Add current conditions if available (for today)
        if current:
            code = current.get('weather_code', 0) or 0
            result["current"] = {
                "temperature": current.get('temperature_2m'),
                "feels_like": current.get('apparent_temperature'),
                "humidity": current.get('relative_humidity_2m'),
                "conditions": weather_codes.get(code, f"Code {code}"),
                "wind_speed": current.get('wind_speed_10m')
            }
        
        if daily:
            code = daily.get('weather_code', [0])[0] or 0
            result["daily"] = {
                "high": daily.get('temperature_2m_max', [None])[0],
                "low": daily.get('temperature_2m_min', [None])[0],
                "conditions": weather_codes.get(code, f"Code {code}"),
                "precipitation": daily.get('precipitation_sum', [0])[0]
            }
        
        if hour is not None and hourly:
            times = hourly.get('time', [])
            for i, t in enumerate(times):
                if f"T{hour:02d}:" in t:
                    code = hourly.get('weather_code', [])[i] if i < len(hourly.get('weather_code', [])) else 0
                    result["hourly"] = {
                        "hour": hour,
                        "time": t,
                        "temperature": hourly.get('temperature_2m', [])[i],
                        "humidity": hourly.get('relative_humidity_2m', [])[i],
                        "conditions": weather_codes.get(code or 0, f"Code {code}"),
                        "wind_speed": hourly.get('wind_speed_10m', [])[i]
                    }
                    break
        
        return result
        
    except Exception as e:
        return {"success": False, "error": str(e)}


def convert_datetime_between_timezones(
    datetime_str: str,
    from_timezone: str,
    to_timezone: str
) -> Dict[str, Any]:
    """
    Convert a datetime from one timezone to another.
    
    Args:
        datetime_str: DateTime in ISO format (YYYY-MM-DDTHH:MM:SS or YYYY-MM-DD HH:MM:SS)
        from_timezone: Source timezone (e.g., "America/Los_Angeles", "UTC", "EST")
        to_timezone: Target timezone
    """
    try:
        # Use timeapi.io conversion API
        # Clean up datetime format
        dt_clean = datetime_str.replace(" ", "T")
        if len(dt_clean) == 10:  # Just date
            dt_clean += "T12:00:00"
        
        url = f"https://timeapi.io/api/Conversion/ConvertTimeZone"
        
        payload = {
            "fromTimeZone": from_timezone,
            "dateTime": dt_clean,
            "toTimeZone": to_timezone,
            "dstAmbiguity": ""
        }
        
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'User-Agent': 'LLMCouncil/1.0',
                'Content-Type': 'application/json'
            },
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
        
        return {
            "success": True,
            "original": {
                "datetime": datetime_str,
                "timezone": from_timezone
            },
            "converted": {
                "datetime": data.get('conversionResult', {}).get('dateTime', ''),
                "timezone": to_timezone,
                "utc_offset": data.get('conversionResult', {}).get('offset', '')
            }
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


def calculate_datetime_offset(
    datetime_str: str,
    days: int = 0,
    hours: int = 0,
    minutes: int = 0
) -> Dict[str, Any]:
    """
    Add or subtract time from a datetime.
    
    Args:
        datetime_str: DateTime in ISO format
        days: Days to add (negative to subtract)
        hours: Hours to add (negative to subtract)
        minutes: Minutes to add (negative to subtract)
    """
    try:
        # Parse the datetime
        dt_clean = datetime_str.replace("T", " ").split(".")[0]
        
        # Try different formats
        for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"]:
            try:
                dt = datetime.strptime(dt_clean, fmt)
                break
            except ValueError:
                continue
        else:
            return {"success": False, "error": f"Could not parse datetime: {datetime_str}"}
        
        # Calculate offset
        offset = timedelta(days=days, hours=hours, minutes=minutes)
        result_dt = dt + offset
        
        return {
            "success": True,
            "original": datetime_str,
            "offset": {
                "days": days,
                "hours": hours,
                "minutes": minutes
            },
            "result": result_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "result_date": result_dt.strftime("%Y-%m-%d"),
            "result_time": result_dt.strftime("%H:%M:%S")
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_daylight_savings_info(location_name: str, date: str) -> Dict[str, Any]:
    """
    Get daylight savings information for a location and date.
    
    Args:
        location_name: City or place name
        date: Date in YYYY-MM-DD format
    """
    try:
        # Geocode location
        geo = geocode_location(location_name)
        if not geo.get('success'):
            return geo
        
        # Get timezone info
        tz_info = get_timezone_for_coordinates(geo['latitude'], geo['longitude'])
        if not tz_info.get('success'):
            return tz_info
        
        # For detailed DST info, we'd need a more sophisticated API
        # For now, return what we can determine
        return {
            "success": True,
            "location": geo['display_name'],
            "timezone": tz_info['timezone'],
            "date": date,
            "is_dst_active": tz_info['is_dst'],
            "current_utc_offset_hours": tz_info['utc_offset'],
            "note": "DST status reflects current time. For historical DST transitions, consult tz database."
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


# Import urllib.parse for URL encoding
import urllib.parse


# Tool definitions
TOOLS = [
    {
        "name": "get-coordinates-for-location",
        "description": "Get longitude and latitude coordinates for a location specified by name (city, address, landmark)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "location_name": {
                    "type": "string",
                    "description": "Location name (e.g., 'Seattle, WA', 'Tokyo, Japan', 'Eiffel Tower')"
                }
            },
            "required": ["location_name"]
        }
    },
    {
        "name": "get-timezone-for-location",
        "description": "Get timezone information for a location specified by name",
        "inputSchema": {
            "type": "object",
            "properties": {
                "location_name": {
                    "type": "string",
                    "description": "Location name (e.g., 'New York', 'London', 'Sydney')"
                }
            },
            "required": ["location_name"]
        }
    },
    {
        "name": "get-current-time-for-location",
        "description": "Get the current local time for a location specified by name",
        "inputSchema": {
            "type": "object",
            "properties": {
                "location_name": {
                    "type": "string",
                    "description": "Location name (e.g., 'Paris', 'Los Angeles')"
                }
            },
            "required": ["location_name"]
        }
    },
    {
        "name": "get-weather-for-location-and-date",
        "description": "Get weather for a location name and specific date. Supports historical data (back to 1940) and forecasts (up to 16 days ahead).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "location_name": {
                    "type": "string",
                    "description": "Location name (e.g., 'Chicago', 'Berlin, Germany')"
                },
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format"
                },
                "hour": {
                    "type": "integer",
                    "description": "Optional hour (0-23) for specific time weather"
                }
            },
            "required": ["location_name", "date"]
        }
    },
    {
        "name": "convert-datetime-between-timezones",
        "description": "Convert a datetime from one timezone to another",
        "inputSchema": {
            "type": "object",
            "properties": {
                "datetime_str": {
                    "type": "string",
                    "description": "DateTime in format YYYY-MM-DDTHH:MM:SS or YYYY-MM-DD HH:MM:SS"
                },
                "from_timezone": {
                    "type": "string",
                    "description": "Source timezone (e.g., 'America/New_York', 'UTC', 'Europe/London')"
                },
                "to_timezone": {
                    "type": "string",
                    "description": "Target timezone"
                }
            },
            "required": ["datetime_str", "from_timezone", "to_timezone"]
        }
    },
    {
        "name": "calculate-datetime-offset",
        "description": "Add or subtract days/hours/minutes from a datetime",
        "inputSchema": {
            "type": "object",
            "properties": {
                "datetime_str": {
                    "type": "string",
                    "description": "DateTime in format YYYY-MM-DD or YYYY-MM-DD HH:MM:SS"
                },
                "days": {
                    "type": "integer",
                    "description": "Days to add (negative to subtract)"
                },
                "hours": {
                    "type": "integer",
                    "description": "Hours to add (negative to subtract)"
                },
                "minutes": {
                    "type": "integer",
                    "description": "Minutes to add (negative to subtract)"
                }
            },
            "required": ["datetime_str"]
        }
    },
    {
        "name": "get-daylight-savings-info",
        "description": "Get daylight savings time information for a location and date",
        "inputSchema": {
            "type": "object",
            "properties": {
                "location_name": {
                    "type": "string",
                    "description": "Location name"
                },
                "date": {
                    "type": "string",
                    "description": "Date in YYYY-MM-DD format"
                }
            },
            "required": ["location_name", "date"]
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
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "location-time", "version": "1.0.0"}
            }
        
        elif method == "notifications/initialized":
            return None
        
        elif method == "tools/list":
            response["result"] = {"tools": TOOLS}
        
        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            if tool_name == "get-coordinates-for-location":
                result = get_coordinates_for_location(arguments.get("location_name"))
            elif tool_name == "get-timezone-for-location":
                result = get_timezone_for_location(arguments.get("location_name"))
            elif tool_name == "get-current-time-for-location":
                result = get_current_time_for_location(arguments.get("location_name"))
            elif tool_name == "get-weather-for-location-and-date":
                result = get_weather_for_location_and_date(
                    arguments.get("location_name"),
                    arguments.get("date"),
                    arguments.get("hour")
                )
            elif tool_name == "convert-datetime-between-timezones":
                result = convert_datetime_between_timezones(
                    arguments.get("datetime_str"),
                    arguments.get("from_timezone"),
                    arguments.get("to_timezone")
                )
            elif tool_name == "calculate-datetime-offset":
                result = calculate_datetime_offset(
                    arguments.get("datetime_str"),
                    arguments.get("days", 0),
                    arguments.get("hours", 0),
                    arguments.get("minutes", 0)
                )
            elif tool_name == "get-daylight-savings-info":
                result = get_daylight_savings_info(
                    arguments.get("location_name"),
                    arguments.get("date")
                )
            else:
                response["error"] = {"code": -32601, "message": f"Unknown tool: {tool_name}"}
                return response
            
            response["result"] = {
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}]
            }
        
        else:
            response["error"] = {"code": -32601, "message": f"Unknown method: {method}"}
    
    except Exception as e:
        response["error"] = {"code": -32000, "message": str(e)}
    
    return response


def main():
    """Main entry point for the MCP server."""
    from mcp_servers.http_wrapper import stdio_main
    stdio_main(handle_request, "Location-Time MCP")


if __name__ == "__main__":
    main()
