import os
import requests
from django.core.cache import cache

ORS_GEOCODE_API_KEY = os.environ["ORS_GEOCODE_API_KEY"]

class GeocodeError(Exception):
    def __init__(self, message, status_code=422):
        self.message = message
        self.status_code = status_code

def geocode(address: str) -> dict:
    address = address.strip()
    
    # Check if raw lat,lng
    parts = address.split(",")
    if len(parts) == 2:
        try:
            lat = float(parts[0].strip())
            lng = float(parts[1].strip())
            return {"lat": lat, "lng": lng, "label": f"{lat}, {lng}"}
        except ValueError:
            pass

    cache_key = f"geocode_{address.lower()}"
    cached_result = cache.get(cache_key)
    if cached_result:
        return cached_result

    url = "https://api.openrouteservice.org/geocode/search"
    headers = {"Authorization": ORS_GEOCODE_API_KEY}
    params = {"text": address, "size": 1}
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=5)
        response.raise_for_status()
    except requests.RequestException:
        raise GeocodeError("Geocoding service unavailable. Please try again.", status_code=503)
        
    data = response.json()
    if not data.get("features"):
        raise GeocodeError(f"Couldn't find '{address}'. Try a more specific address.", status_code=422)
        
    feature = data["features"][0]
    lng, lat = feature["geometry"]["coordinates"]
    label = feature["properties"].get("label", address)
    
    result = {"lat": lat, "lng": lng, "label": label}
    cache.set(cache_key, result, timeout=86400) # cache for 24h
    return result
