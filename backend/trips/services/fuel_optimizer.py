"""Fuel purchases along a fixed ORS route using the assessment price snapshot."""

import json
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from functools import lru_cache
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

MAX_RANGE_MILES = 500.0
MILES_PER_GALLON = 10.0
TANK_GALLONS = MAX_RANGE_MILES / MILES_PER_GALLON
MAX_ROUTE_OFFSET_MILES = 10.0
GRID_MILES = 20.0


class NoFuelPlan(Exception):
    pass


@dataclass(frozen=True)
class Candidate:
    station_id: str
    name: str
    address: str
    city: str
    state: str
    price: Decimal
    latitude: float
    longitude: float
    mile: float
    route_offset: float


@lru_cache(maxsize=1)
def load_stations():
    path = Path(__file__).resolve().parent.parent / "data" / "fuel_stations.json"
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def _geodesic_miles(start, end):
    """Great-circle length of a route segment, used for route mile markers."""
    lon1, lat1 = start
    lon2, lat2 = end
    lat1, lat2 = radians(lat1), radians(lat2)
    half_lat = sin((lat2 - lat1) / 2) ** 2
    half_lon = cos(lat1) * cos(lat2) * sin(radians(lon2 - lon1) / 2) ** 2
    return 3958.7613 * 2 * asin(sqrt(min(1.0, half_lat + half_lon)))


def project_stations(geometry, total_miles, stations=None):
    """Index route segments in 20-mile cells and find stations within 10 miles."""
    if len(geometry) < 2 or total_miles <= 0:
        raise NoFuelPlan("Route geometry has no usable length.")
    if stations is None:
        stations = load_stations()
    mean_lat = sum(point[1] for point in geometry) / len(geometry)
    x_scale = 69.172 * max(cos(radians(mean_lat)), 0.01)
    y_scale = 69.0
    points = [(lon * x_scale, lat * y_scale) for lon, lat in geometry]
    segments = []
    cells = {}
    road_length = 0.0
    for position, ((ax, ay), (bx, by)) in enumerate(zip(points, points[1:])):
        dx, dy = bx - ax, by - ay
        seg_len = (dx * dx + dy * dy) ** 0.5
        if seg_len < 1e-9:
            continue
        road_segment_length = _geodesic_miles(geometry[position], geometry[position + 1])
        segment = (ax, ay, dx, dy, seg_len, road_segment_length, road_length)
        index = len(segments)
        segments.append(segment)
        for ix in range(int((min(ax, bx) - MAX_ROUTE_OFFSET_MILES) // GRID_MILES),
                        int((max(ax, bx) + MAX_ROUTE_OFFSET_MILES) // GRID_MILES) + 1):
            for iy in range(int((min(ay, by) - MAX_ROUTE_OFFSET_MILES) // GRID_MILES),
                            int((max(ay, by) + MAX_ROUTE_OFFSET_MILES) // GRID_MILES) + 1):
                cells.setdefault((ix, iy), []).append(index)
        road_length += road_segment_length
    if not segments:
        raise NoFuelPlan("Route geometry has no usable length.")

    candidates = []
    for station in stations:
        station_id, name, address, city, state, price, latitude, longitude = station
        px, py = longitude * x_scale, latitude * y_scale
        nearby = cells.get((int(px // GRID_MILES), int(py // GRID_MILES)), ())
        best_distance_sq = MAX_ROUTE_OFFSET_MILES ** 2
        best_mile = None
        for index in nearby:
            ax, ay, dx, dy, seg_len, road_segment_length, before = segments[index]
            t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (seg_len * seg_len)))
            distance_sq = (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2
            if distance_sq <= best_distance_sq:
                best_distance_sq = distance_sq
                best_mile = total_miles * (before + t * road_segment_length) / road_length
        if best_mile is not None:
            candidates.append(Candidate(
                str(station_id), name, address, city, state, Decimal(str(price)),
                latitude, longitude, best_mile, best_distance_sq ** 0.5,
            ))
    return sorted(candidates, key=lambda item: (item.mile, item.price, item.station_id))


def optimize_purchases(total_miles, candidates, starting_gallons=50.0):
    """Buy enough to reach the first cheaper station; otherwise fill the tank."""
    if not 0 <= starting_gallons <= TANK_GALLONS:
        raise ValueError("starting_gallons must be between 0 and 50")
    stations = [item for item in candidates if 0 <= item.mile < total_miles]
    remaining = float(starting_gallons)
    previous_mile = 0.0
    total_cost = Decimal("0")
    stops = []
    for index, station in enumerate(stations):
        remaining -= (station.mile - previous_mile) / MILES_PER_GALLON
        if remaining < -1e-7:
            raise NoFuelPlan("No reachable priced station covers this route segment.")
        remaining = max(remaining, 0.0)
        previous_mile = station.mile
        cheaper_mile = None
        for next_station in stations[index + 1:]:
            if next_station.mile - station.mile > MAX_RANGE_MILES + 1e-7:
                break
            if next_station.price < station.price:
                cheaper_mile = next_station.mile
                break
        if total_miles - station.mile <= MAX_RANGE_MILES and cheaper_mile is None:
            cheaper_mile = total_miles
        target = TANK_GALLONS if cheaper_mile is None else (cheaper_mile - station.mile) / MILES_PER_GALLON
        gallons = max(0.0, min(TANK_GALLONS, target) - remaining)
        if gallons > 1e-7:
            cost = (Decimal(str(gallons)) * station.price).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            total_cost += cost
            remaining += gallons
            stops.append({
                "station_id": station.station_id, "name": station.name,
                "address": station.address, "city": station.city, "state": station.state,
                "coordinates": [station.longitude, station.latitude],
                "coordinate_source": "city_centroid", "mile_marker": round(station.mile, 1),
                "distance_from_route_miles": round(station.route_offset, 1),
                "price_per_gallon_usd": str(station.price),
                "gallons": round(gallons, 3), "cost_usd": str(cost),
            })
    remaining -= (total_miles - previous_mile) / MILES_PER_GALLON
    if remaining < -1e-7:
        raise NoFuelPlan("No reachable priced station covers this route segment.")
    return {
        "fuel_stops": stops,
        "total_money_spent_on_fuel_usd": str(total_cost),
        "fuel_consumed_gallons": round(total_miles / MILES_PER_GALLON, 3),
        "fuel_remaining_at_finish_gallons": round(max(0.0, remaining), 3),
    }
