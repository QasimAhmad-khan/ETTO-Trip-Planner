"""USA geocoding and a single directions request through ETTO's ORS account."""

import hashlib
import json
import os

import requests
from django.core.cache import cache


class FuelRoutingError(Exception):
    pass


class FuelLocationError(FuelRoutingError):
    pass


def _key(kind):
    return os.environ.get(f"ORS_{kind}_API_KEY") or os.environ.get("ORS_API_KEY")


def _request(method, url, key, **kwargs):
    try:
        response = requests.request(method, url, headers={"Authorization": key}, timeout=15, **kwargs)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise FuelRoutingError("The map and routing service is unavailable. Please try again.") from exc


def geocode_us(query):
    normalized = " ".join(query.strip().split())
    cache_key = "fuel_geocode:" + hashlib.sha256(normalized.casefold().encode()).hexdigest()
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    data = _request(
        "GET", "https://api.openrouteservice.org/geocode/search", _key("GEOCODE"),
        params={"text": normalized, "boundary.country": "USA", "size": 5},
    )
    for feature in data.get("features", []):
        properties = feature.get("properties", {})
        coordinates = feature.get("geometry", {}).get("coordinates", [])
        if str(properties.get("country_a", "")).upper() == "USA" and len(coordinates) >= 2:
            result = {"label": properties.get("label", normalized), "coordinates": coordinates[:2]}
            cache.set(cache_key, result, 86400)
            return result
    raise FuelLocationError(f"Could not resolve a location in the USA: {normalized}")


def directions(start, finish):
    key_material = json.dumps([start["coordinates"], finish["coordinates"]], separators=(",", ":"))
    cache_key = "fuel_directions:" + hashlib.sha256(key_material.encode()).hexdigest()
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    data = _request(
        "POST", "https://api.openrouteservice.org/v2/directions/driving-car/geojson",
        _key("DIRECTIONS"), json={"coordinates": [start["coordinates"], finish["coordinates"]],
                                    "options": {"avoid_borders": "all"}},
    )
    try:
        feature = data["features"][0]
        geometry = feature["geometry"]["coordinates"]
        meters = float(feature["properties"]["summary"]["distance"])
        if len(geometry) < 2 or meters <= 0:
            raise ValueError("Empty route")
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise FuelRoutingError("No usable driving route was returned for these locations.") from exc
    route = {"distance_miles": meters / 1609.344, "geometry": geometry}
    cache.set(cache_key, route, 3600)
    return route
