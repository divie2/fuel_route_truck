from unittest.mock import patch

import requests
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from fuelroute.models import City, FuelStation
from fuelroute.services.places import normalize_city
from fuelroute.services.station_index import clear_station_cache

# A straight east-west route along latitude 40, from lon -100 to lon -90 (~530 miles).
ROUTE_COORDS = [[-100 + i * 0.5, 40.0] for i in range(21)]
ROUTE_METERS = 530 * 1609.344


def osrm_ok():
    return {
        "code": "Ok",
        "routes": [
            {
                "distance": ROUTE_METERS,
                "duration": 8 * 3600,
                "geometry": {"type": "LineString", "coordinates": ROUTE_COORDS},
            }
        ],
    }


@patch("fuelroute.services.routing.requests.get")
class RoutePlanApiTests(TestCase):
    url = reverse("fuelroute:route-plan")
    body = {"start": "Alpha, KS", "finish": "Omega, MO"}

    @classmethod
    def setUpTestData(cls):
        for name, state, lon in [("Alpha", "KS", -100.0), ("Omega", "MO", -90.0)]:
            City.objects.create(
                name=name, state=state, search_key=normalize_city(name), latitude=40.0, longitude=lon
            )
        # Expensive at the start, cheap in the middle, mid-priced near the end.
        for opis_id, lon, price in [(1, -100.0, "4.000"), (2, -95.0, "3.000"), (3, -91.0, "3.500")]:
            FuelStation.objects.create(
                opis_id=opis_id, name=f"Station {opis_id}", address="I-70", city="X",
                state="KS", price=price, latitude=40.0, longitude=lon,
            )

    def setUp(self):
        cache.clear()
        clear_station_cache()
        self.addCleanup(clear_station_cache)

    def test_post_returns_cheapest_plan(self, mock_get):
        mock_get.return_value.json.return_value = osrm_ok()

        response = self.client.post(self.url, self.body, content_type="application/json")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual([s["opis_id"] for s in data["fuel_stops"]], [1, 2])
        self.assertAlmostEqual(data["summary"]["total_gallons"], 53.0, delta=0.2)
        self.assertGreater(data["summary"]["total_fuel_cost"], 0)
        self.assertEqual(data["route"]["geometry"]["type"], "LineString")
        self.assertIn("/api/route/map/?start=Alpha", data["map_url"])
        self.assertEqual(data["meta"]["routing_api_calls"], 1)
        self.assertEqual(data["meta"]["geocoding_api_calls"], 0)

    def test_second_request_is_served_from_cache(self, mock_get):
        mock_get.return_value.json.return_value = osrm_ok()

        self.client.post(self.url, self.body, content_type="application/json")
        response = self.client.get(self.url, self.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["meta"]["routing_api_calls"], 0)
        self.assertEqual(mock_get.call_count, 1)

    def test_missing_field_returns_400(self, mock_get):
        response = self.client.post(self.url, {"start": "Alpha, KS"}, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        mock_get.assert_not_called()

    def test_location_outside_usa_returns_400(self, mock_get):
        response = self.client.post(
            self.url, {"start": "Toronto, ON", "finish": "Omega, MO"}, content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "invalid_location")

    def test_routing_failure_returns_502(self, mock_get):
        mock_get.side_effect = requests.ConnectionError("down")
        response = self.client.post(self.url, self.body, content_type="application/json")
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"]["code"], "routing_failed")

    def test_no_stations_on_route_returns_422(self, mock_get):
        mock_get.return_value.json.return_value = osrm_ok()
        FuelStation.objects.all().delete()
        response = self.client.post(self.url, self.body, content_type="application/json")
        self.assertEqual(response.status_code, 422)

    def test_map_page_renders(self, mock_get):
        mock_get.return_value.json.return_value = osrm_ok()
        response = self.client.get(reverse("fuelroute:route-map"), self.body)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "leaflet")
        self.assertContains(response, "Station 2")
