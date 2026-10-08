"""Checks for route projection, optimal purchases, and the public API contract."""

from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.test import APIClient

from trips.services.fuel_optimizer import Candidate, NoFuelPlan, load_stations, optimize_purchases, project_stations
from trips.services.fuel_routing import FuelLocationError, FuelRoutingError, directions, geocode_us


def candidate(mile, price, station_id=None):
    return Candidate(str(station_id or mile), "Test Stop", "Main St", "Town", "TX",
                     Decimal(str(price)), 32.0, -96.0, mile, 0.0)


class OptimizerTests(SimpleTestCase):
    def test_assessment_snapshot_is_loaded(self):
        stations = load_stations()
        self.assertEqual(len(stations), 6598)
        self.assertEqual(len(stations[0]), 8)

    def test_first_cheaper_station_gets_only_required_fuel(self):
        plan = optimize_purchases(700, [candidate(450, 4), candidate(600, 3)])
        self.assertEqual([stop["mile_marker"] for stop in plan["fuel_stops"]], [450, 600])
        self.assertAlmostEqual(plan["fuel_stops"][0]["gallons"], 10)

    def test_cheap_station_fills_when_no_cheaper_one_is_reachable(self):
        plan = optimize_purchases(900, [candidate(400, 3), candidate(800, 4)])
        self.assertEqual([stop["mile_marker"] for stop in plan["fuel_stops"]], [400])
        self.assertEqual(plan["fuel_stops"][0]["gallons"], 40)
        self.assertEqual(plan["total_money_spent_on_fuel_usd"], "120.00")

    def test_cheaper_station_buys_just_enough_to_finish(self):
        plan = optimize_purchases(800, [candidate(400, 4), candidate(600, 2)])
        self.assertEqual([stop["gallons"] for stop in plan["fuel_stops"]], [10, 20])
        self.assertEqual(plan["total_money_spent_on_fuel_usd"], "80.00")

    def test_short_route_needs_no_purchase_with_full_tank(self):
        plan = optimize_purchases(300, [])
        self.assertEqual(plan["fuel_stops"], [])
        self.assertEqual(plan["total_money_spent_on_fuel_usd"], "0")

    def test_unreachable_gap_is_rejected(self):
        with self.assertRaises(NoFuelPlan):
            optimize_purchases(1100, [candidate(400, 3)])

    def test_projection_rejects_far_stations(self):
        geometry = [[-100, 40], [-99, 40]]
        near = ["1", "Near", "A", "Town", "KS", 3.5, 40.01, -99.5]
        far = ["2", "Far", "B", "Town", "KS", 2.0, 41.0, -99.5]
        result = project_stations(geometry, 52, [near, far])
        self.assertEqual([station.station_id for station in result], ["1"])
        self.assertAlmostEqual(result[0].mile, 26, delta=0.1)

    def test_projection_uses_geographic_lengths_across_latitudes(self):
        geometry = [[-100, 30], [-90, 30], [-90, 50], [-80, 50]]
        station = ["1", "Latitude Stop", "A", "Town", "CO", 3.5, 50, -90]
        result = project_stations(geometry, 1000, [station])
        self.assertEqual(len(result), 1)
        self.assertGreater(result[0].mile, 810)
        self.assertLess(result[0].mile, 825)


class FuelApiTests(SimpleTestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/fuel/route"

    def test_bad_inputs_fail_before_provider_calls(self):
        for payload in ({"start": "Dallas", "finish": "Dallas"},
                        {"start": "Dallas", "finish": "Denver", "starting_fuel_gallons": 51},
                        {"start": "", "finish": "Denver"}):
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post(self.url, payload, format="json").status_code, 400)

    @patch.dict("os.environ", {"ORS_GEOCODE_API_KEY": "test", "ORS_DIRECTIONS_API_KEY": "test"})
    @patch("trips.fuel_views.optimize_purchases")
    @patch("trips.fuel_views.project_stations")
    @patch("trips.fuel_views.directions")
    @patch("trips.fuel_views.geocode_us")
    def test_response_contains_route_stops_and_total(self, geocode, route, project, optimize):
        geocode.side_effect = [
            {"label": "Dallas, TX", "coordinates": [-96, 32]},
            {"label": "Denver, CO", "coordinates": [-105, 40]},
        ]
        route.return_value = {"distance_miles": 800, "geometry": [[-96, 32], [-105, 40]]}
        project.return_value = [candidate(400, 3)]
        optimize.return_value = {"fuel_stops": [{"station_id": "400", "coordinates": [-96, 32],
                                "price_per_gallon_usd": "3.00"}],
                                 "total_money_spent_on_fuel_usd": "90.00",
                                 "fuel_consumed_gallons": 80, "fuel_remaining_at_finish_gallons": 0}
        response = self.client.post(self.url, {"start": "Dallas, TX", "finish": "Denver, CO"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["map_geojson"]["features"][0]["properties"]["kind"], "route")
        self.assertEqual(len(response.data["map_geojson"]["features"]), 4)
        self.assertEqual(response.data["total_money_spent_on_fuel_usd"], "90.00")
        optimize.assert_called_once()

    @patch.dict("os.environ", {"ORS_GEOCODE_API_KEY": "test", "ORS_DIRECTIONS_API_KEY": "test"})
    @patch("trips.fuel_views.geocode_us", side_effect=FuelLocationError("Outside USA"))
    def test_non_us_location_returns_422(self, _geocode):
        response = self.client.post(self.url, {"start": "Toronto", "finish": "Dallas"}, format="json")
        self.assertEqual(response.status_code, 422)

    @patch.dict("os.environ", {"ORS_GEOCODE_API_KEY": "test", "ORS_DIRECTIONS_API_KEY": "test"})
    @patch("trips.fuel_views.geocode_us", side_effect=FuelRoutingError("Provider down"))
    def test_upstream_failure_returns_502(self, _geocode):
        response = self.client.post(self.url, {"start": "Dallas", "finish": "Denver"}, format="json")
        self.assertEqual(response.status_code, 502)


class ProviderCallTests(SimpleTestCase):
    @patch("trips.services.fuel_routing._request")
    def test_geocoder_filters_usa_and_caches(self, request):
        request.return_value = {"features": [
            {"properties": {"country_a": "CAN"}, "geometry": {"coordinates": [-79, 43]}},
            {"properties": {"country_a": "USA", "label": "Austin, TX"},
             "geometry": {"coordinates": [-97, 30]}},
        ]}
        first = geocode_us("Austin, TX")
        second = geocode_us(" Austin, TX ")
        self.assertEqual(first, second)
        request.assert_called_once()

    @patch("trips.services.fuel_routing._request")
    def test_explicit_foreign_country_is_not_resolved_to_us_namesake(self, request):
        request.return_value = {"features": [{
            "properties": {"country_a": "USA", "country": "United States",
                           "region": "Ohio", "region_a": "OH", "label": "Toronto, OH, USA"},
            "geometry": {"coordinates": [-80.606, 40.457]},
        }]}
        with self.assertRaises(FuelLocationError):
            geocode_us("Toronto, Canada")

    @patch("trips.services.fuel_routing._request")
    def test_explicit_us_state_must_match_result(self, request):
        request.return_value = {"features": [{
            "properties": {"country_a": "USA", "region_a": "OH", "label": "Toronto, OH, USA"},
            "geometry": {"coordinates": [-80.606, 40.457]},
        }]}
        with self.assertRaises(FuelLocationError):
            geocode_us("Toronto, ON")

    @patch("trips.services.fuel_routing._request")
    def test_directions_uses_one_route_call(self, request):
        request.return_value = {"features": [{"geometry": {"coordinates": [[-100, 40], [-99, 40]]},
                                               "properties": {"summary": {"distance": 100000}}}]}
        start = {"coordinates": [-100, 40]}
        finish = {"coordinates": [-99, 40]}
        route = directions(start, finish)
        self.assertAlmostEqual(route["distance_miles"], 62.137, places=2)
        self.assertEqual(request.call_count, 1)
