from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils.timezone import now
import datetime
from .serializers import TripPlanSerializer
from .services.geocode import geocode, GeocodeError
from .services.routing import get_route, chunk_drive_with_fuel_coords, _decode_ors_polyline
from .services.hos_engine import run_simulation, UnitOfWork
from .services.log_builder import build_logs


class HealthCheckView(APIView):
    def get(self, request):
        return Response({"status": "ok"})


class TripPlanView(APIView):
    def post(self, request):
        serializer = TripPlanSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        try:
            current = geocode(data["current_location"])
            pickup  = geocode(data["pickup_location"])
            dropoff = geocode(data["dropoff_location"])

            units = []
            legs = []
            geometry = []
            warnings = []
            all_fuel_coords = []   # ordered list of [lat,lng] | None for every fuel stop

            # ── Leg 1: Current → Pickup ───────────────────────────────────────
            same_start = (current["lat"] == pickup["lat"] and current["lng"] == pickup["lng"])
            if not same_start:
                route1 = get_route(current, pickup)
                if route1["distance_mi"] > 0:
                    pts1 = _decode_ors_polyline(route1["geometry"])
                    u1, fc1 = chunk_drive_with_fuel_coords(
                        route1["distance_mi"], route1["duration_hours"],
                        f"Drive to {pickup['label']}", pts1
                    )
                    units.extend(u1)
                    all_fuel_coords.extend(fc1)
                    legs.append({
                        "from": current["label"],
                        "to": pickup["label"],
                        "distance_mi": route1["distance_mi"],
                        "drive_hours": route1["duration_hours"]
                    })
                    geometry.append(route1["geometry"])
                    if "warnings" in route1:
                        warnings.extend(route1["warnings"])

            # ── Pickup ────────────────────────────────────────────────────────
            if data.get("use_ym", True):
                units.append(UnitOfWork("YM", 0.25, 0.0, f"Yard Move: {pickup['label']}"))
                units.append(UnitOfWork("ON", 0.75, 0.0, f"Pickup: {pickup['label']}"))
            else:
                units.append(UnitOfWork("ON", 1.0, 0.0, f"Pickup: {pickup['label']}"))

            # ── Leg 2: Pickup → Dropoff ───────────────────────────────────────
            same_dest = (pickup["lat"] == dropoff["lat"] and pickup["lng"] == dropoff["lng"])
            if not same_dest:
                route2 = get_route(pickup, dropoff)
                if route2["distance_mi"] > 0:
                    pts2 = _decode_ors_polyline(route2["geometry"])
                    u2, fc2 = chunk_drive_with_fuel_coords(
                        route2["distance_mi"], route2["duration_hours"],
                        f"Drive to {dropoff['label']}", pts2
                    )
                    units.extend(u2)
                    all_fuel_coords.extend(fc2)
                    legs.append({
                        "from": pickup["label"],
                        "to": dropoff["label"],
                        "distance_mi": route2["distance_mi"],
                        "drive_hours": route2["duration_hours"]
                    })
                    geometry.append(route2["geometry"])
                    if "warnings" in route2:
                        warnings.extend(route2["warnings"])

            # ── Dropoff ───────────────────────────────────────────────────────
            if data.get("use_ym", True):
                units.append(UnitOfWork("YM", 0.25, 0.0, f"Yard Move: {dropoff['label']}"))
                units.append(UnitOfWork("ON", 0.75, 0.0, f"Dropoff: {dropoff['label']}"))
            else:
                units.append(UnitOfWork("ON", 1.0, 0.0, f"Dropoff: {dropoff['label']}"))

            # ── Personal Conveyance ───────────────────────────────────────────
            if data.get("use_pc", False):
                units.append(UnitOfWork("PC", 0.5, 0.0, "Personal Conveyance"))

            # ── Input metrics (pre-simulation) ────────────────────────────────
            total_distance = sum(u.distance_mi for u in units)

            # ── HOS simulation ────────────────────────────────────────────────
            start_time = data.get("start_time") or now()
            segments = run_simulation(units, data["current_cycle_used"])

            # ── Post-simulation metrics ───────────────────────────────────────
            total_drive     = sum(s.duration_hours for s in segments if s.status == "D")
            total_on_duty   = sum(s.duration_hours for s in segments if s.status in ("D", "ON"))
            total_elapsed   = sum(s.duration_hours for s in segments)

            # ── Build log sheets ──────────────────────────────────────────────
            logs = build_logs(segments, start_time, total_distance)

            # ── Build detailed stops list with timing ─────────────────────────
            fuel_iter = iter(all_fuel_coords)
            current_t = start_time
            stops = [{
                "type": "start",
                "lat": current["lat"],
                "lng": current["lng"],
                "label": current["label"],
                "start": start_time.isoformat(),
                "duration_hours": 0
            }]

            for seg in segments:
                lbl = (seg.label or "").lower()
                stop = None

                if seg.status == "ON" and "pickup" in lbl:
                    stop = {
                        "type": "pickup",
                        "lat": pickup["lat"],
                        "lng": pickup["lng"],
                        "label": seg.label,
                        "start": current_t.isoformat(),
                        "duration_hours": round(seg.duration_hours, 2)
                    }
                elif seg.status == "ON" and "dropoff" in lbl:
                    stop = {
                        "type": "dropoff",
                        "lat": dropoff["lat"],
                        "lng": dropoff["lng"],
                        "label": seg.label,
                        "start": current_t.isoformat(),
                        "duration_hours": round(seg.duration_hours, 2)
                    }
                elif seg.status == "ON" and "fuel" in lbl:
                    coord = next(fuel_iter, None)
                    stop = {
                        "type": "fuel",
                        "label": seg.label,
                        "start": current_t.isoformat(),
                        "duration_hours": round(seg.duration_hours, 2)
                    }
                    if coord:
                        stop["lat"] = coord[0]
                        stop["lng"] = coord[1]
                elif seg.status == "OFF" and "restart" in lbl:
                    stop = {
                        "type": "restart",
                        "label": seg.label,
                        "start": current_t.isoformat(),
                        "duration_hours": round(seg.duration_hours, 2)
                    }
                elif seg.status == "OFF" and ("reset" in lbl or "off duty" in lbl):
                    stop = {
                        "type": "reset",
                        "label": seg.label,
                        "start": current_t.isoformat(),
                        "duration_hours": round(seg.duration_hours, 2)
                    }
                elif seg.status == "OFF" and "break" in lbl:
                    stop = {
                        "type": "break",
                        "label": seg.label,
                        "start": current_t.isoformat(),
                        "duration_hours": round(seg.duration_hours, 2)
                    }

                if stop:
                    stops.append(stop)

                current_t += datetime.timedelta(hours=seg.duration_hours)

            response_data = {
                "summary": {
                    "total_distance_mi": round(total_distance, 1),
                    "total_drive_hours": round(total_drive, 1),
                    "total_on_duty_hours": round(total_on_duty, 1),
                    "total_elapsed_hours": round(total_elapsed, 1),
                    "days": len(logs),
                    "log_sheets": len(logs),
                    "arrival_time": (start_time + datetime.timedelta(hours=total_elapsed)).isoformat(),
                    "restart_required": any(
                        s.status == "OFF" and s.duration_hours >= 34 for s in segments
                    ),
                    "rounding": "15-minute grid snapping",
                    "warnings": warnings
                },
                "route": {
                    "geometry": geometry,
                    "legs": legs
                },
                "stops": stops,
                "logs": logs
            }
            return Response(response_data)

        except GeocodeError as e:
            return Response({"error": e.message}, status=e.status_code)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error("Internal error during trip planning: %s", e, exc_info=True)
            return Response(
                {"error": "An internal server error occurred while planning the trip."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
