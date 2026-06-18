import os
import math
import requests
from .hos_engine import UnitOfWork
from .geocode import GeocodeError

ORS_DIRECTIONS_API_KEY = os.environ["ORS_DIRECTIONS_API_KEY"]


def _decode_ors_polyline(encoded: str):
    """Decode ORS/Google encoded polyline → list of [lat, lng]."""
    points = []
    index = 0
    lat = 0
    lng = 0
    while index < len(encoded):
        result = 0
        shift = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1f) << shift
            shift += 5
            if b < 0x20:
                break
        dlat = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += dlat
        result = 0
        shift = 0
        while True:
            b = ord(encoded[index]) - 63
            index += 1
            result |= (b & 0x1f) << shift
            shift += 5
            if b < 0x20:
                break
        dlng = ~(result >> 1) if (result & 1) else (result >> 1)
        lng += dlng
        points.append([lat / 1e5, lng / 1e5])
    return points


def _haversine_mi(lat1, lng1, lat2, lng2):
    R = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(min(a, 1.0)))


def _point_at_distance_mi(points, target_mi):
    """Return [lat, lng] interpolated at target_mi along the polyline."""
    if not points:
        return None
    cumulative = 0.0
    for i in range(1, len(points)):
        lat1, lng1 = points[i - 1]
        lat2, lng2 = points[i]
        seg_dist = _haversine_mi(lat1, lng1, lat2, lng2)
        if cumulative + seg_dist >= target_mi:
            frac = (target_mi - cumulative) / seg_dist if seg_dist > 0 else 0
            return [lat1 + frac * (lat2 - lat1), lng1 + frac * (lng2 - lng1)]
        cumulative += seg_dist
    return list(points[-1])

def get_route(start: dict, end: dict, profile='driving-hgv') -> dict:
    url = f"https://api.openrouteservice.org/v2/directions/{profile}"
    headers = {
        "Authorization": ORS_DIRECTIONS_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "coordinates": [[start["lng"], start["lat"]], [end["lng"], end["lat"]]],
        "radiuses": [-1, -1],
        "instructions": False
    }
    
    response = None
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        response = getattr(e, "response", None)
        if response is not None:
            if response.status_code == 404:
                if profile == 'driving-hgv':
                    # Fallback to car if truck routing fails (e.g. city center coordinate is restricted)
                    fallback = get_route(start, end, profile='driving-car')
                    fallback["warnings"] = [f"Fell back to car routing for {start.get('label', 'a location')} to {end.get('label', 'destination')} because heavy goods vehicle routing failed."]
                    return fallback
                raise GeocodeError("No drivable route between these points.", status_code=422)
            
            data = None
            try:
                data = response.json()
            except Exception:
                pass
                
            if data and "error" in data:
                err_msg = data["error"]["message"] if isinstance(data["error"], dict) else str(data["error"])
                raise GeocodeError(f"Routing failed: {err_msg}", status_code=422)
                
            raise GeocodeError(f"Routing service unavailable: HTTP {response.status_code}", status_code=503)
        raise GeocodeError("Routing service unavailable. Please try again.", status_code=503)
        
    data = response.json()
    if "error" in data or not data.get("routes"):
        raise GeocodeError("No drivable route between these points.", status_code=422)
        
    route = data["routes"][0]
    geometry = route["geometry"] # encoded polyline
    summary = route["summary"]
    
    distance_mi = summary["distance"] * 0.000621371
    duration_hours = summary["duration"] / 3600.0
    
    # Fallback if duration is 0 but distance is not
    if duration_hours <= 0 and distance_mi > 0:
        duration_hours = distance_mi / 55.0
        
    return {
        "distance_mi": distance_mi,
        "duration_hours": duration_hours,
        "geometry": geometry
    }

def decompose_into_units(current: dict, pickup: dict, dropoff: dict) -> list:
    """
    Given the three locations, return a list of UnitOfWork objects.
    Also handles inserting fuel stops every 1000 miles.
    """
    units = []
    
    # Check if current != pickup
    if current["lat"] != pickup["lat"] or current["lng"] != pickup["lng"]:
        leg1 = get_route(current, pickup)
        if leg1["distance_mi"] > 0:
            units.extend(_chunk_drive(leg1["distance_mi"], leg1["duration_hours"], f"Drive to {pickup['label']}"))
            
    # Pickup
    units.append(UnitOfWork("ON", 1.0, 0.0, f"Pickup: {pickup['label']}"))
    
    # Check if pickup != dropoff
    if pickup["lat"] != dropoff["lat"] or pickup["lng"] != dropoff["lng"]:
        leg2 = get_route(pickup, dropoff)
        if leg2["distance_mi"] > 0:
            units.extend(_chunk_drive(leg2["distance_mi"], leg2["duration_hours"], f"Drive to {dropoff['label']}"))
            
    # Dropoff
    units.append(UnitOfWork("ON", 1.0, 0.0, f"Dropoff: {dropoff['label']}"))
    
    return units

def chunk_drive_with_fuel_coords(distance_mi: float, duration_hours: float, label: str, leg_points=None):
    """Like _chunk_drive but also returns interpolated [lat,lng] for each fuel stop."""
    units = []
    fuel_coords = []
    remaining_dist = distance_mi
    remaining_dur = duration_hours
    cumulative_in_leg = 0.0

    FUEL_INTERVAL = 1000.0

    while remaining_dist > FUEL_INTERVAL:
        ratio = FUEL_INTERVAL / remaining_dist
        chunk_dur = remaining_dur * ratio
        cumulative_in_leg += FUEL_INTERVAL

        units.append(UnitOfWork("DRIVE", chunk_dur, FUEL_INTERVAL, label))
        units.append(UnitOfWork("ON", 0.5, 0.0, "Fuel Stop"))
        fuel_coords.append(_point_at_distance_mi(leg_points, cumulative_in_leg) if leg_points else None)

        remaining_dist -= FUEL_INTERVAL
        remaining_dur -= chunk_dur

    if remaining_dist > 0:
        units.append(UnitOfWork("DRIVE", remaining_dur, remaining_dist, label))

    return units, fuel_coords


def _chunk_drive(distance_mi: float, duration_hours: float, label: str) -> list:
    """
    Splits a drive leg into chunks to insert fuel stops every 1000 miles.
    """
    units = []
    remaining_dist = distance_mi
    remaining_dur = duration_hours
    
    FUEL_INTERVAL = 1000.0
    
    while remaining_dist > FUEL_INTERVAL:
        ratio = FUEL_INTERVAL / remaining_dist
        chunk_dur = remaining_dur * ratio
        
        units.append(UnitOfWork("DRIVE", chunk_dur, FUEL_INTERVAL, label))
        units.append(UnitOfWork("ON", 0.5, 0.0, "Fuel Stop"))
        
        remaining_dist -= FUEL_INTERVAL
        remaining_dur -= chunk_dur
        
    if remaining_dist > 0:
        units.append(UnitOfWork("DRIVE", remaining_dur, remaining_dist, label))
        
    return units
