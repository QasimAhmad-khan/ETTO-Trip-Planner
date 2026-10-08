"""Fuel-aware route endpoint for the ETTO app and Postman."""

import logging
import os
import time

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import FuelRouteSerializer
from .services.fuel_optimizer import NoFuelPlan, load_stations, optimize_purchases, project_stations
from .services.fuel_routing import FuelLocationError, FuelRoutingError, directions, geocode_us

logger = logging.getLogger(__name__)


class FuelRouteView(APIView):
    def post(self, request):
        serializer = FuelRouteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data
        if not (os.environ.get("ORS_GEOCODE_API_KEY") or os.environ.get("ORS_API_KEY")) or not (
            os.environ.get("ORS_DIRECTIONS_API_KEY") or os.environ.get("ORS_API_KEY")
        ):
            return Response({"error": "Routing is not configured."}, status=503)
        started = time.perf_counter()
        try:
            origin = geocode_us(data["start"])
            destination = geocode_us(data["finish"])
            if origin["coordinates"] == destination["coordinates"]:
                return Response({"error": "Start and finish resolve to the same place."}, status=400)
            route = directions(origin, destination)
            candidates = project_stations(route["geometry"], route["distance_miles"])
            plan = optimize_purchases(route["distance_miles"], candidates, data["starting_fuel_gallons"])
        except FuelLocationError as exc:
            return Response({"error": str(exc)}, status=422)
        except NoFuelPlan as exc:
            return Response({"error": str(exc)}, status=422)
        except FuelRoutingError as exc:
            return Response({"error": str(exc)}, status=502)
        except (OSError, ValueError) as exc:
            logger.error("Fuel data unavailable: %s", exc)
            return Response({"error": "Fuel price data is unavailable."}, status=503)

        features = [{"type": "Feature", "properties": {"kind": "route"},
                     "geometry": {"type": "LineString", "coordinates": route["geometry"]}}]
        for kind, point in (("start", origin), ("finish", destination)):
            features.append({"type": "Feature", "properties": {"kind": kind, "label": point["label"]},
                             "geometry": {"type": "Point", "coordinates": point["coordinates"]}})
        for stop in plan["fuel_stops"]:
            features.append({"type": "Feature", "properties": {"kind": "fuel_stop",
                             "station_id": stop["station_id"], "price_per_gallon_usd": stop["price_per_gallon_usd"]},
                             "geometry": {"type": "Point", "coordinates": stop["coordinates"]}})
        return Response({
            "start": origin, "finish": destination,
            "distance_miles": round(route["distance_miles"], 2),
            "vehicle": {"maximum_range_miles": 500, "miles_per_gallon": 10,
                        "starting_fuel_gallons": data["starting_fuel_gallons"]},
            "map_geojson": {"type": "FeatureCollection", "features": features},
            **plan, "candidate_stations_considered": len(candidates),
            "pricing_note": "Total is fuel bought during this trip; fuel already in the tank is excluded. Station positions use city centroids because the supplied CSV has no coordinates. Detours are not priced.",
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
        })
