from unittest.mock import patch

from django.test import TestCase

from fuelroute.models import City
from fuelroute.services.exceptions import InvalidLocationError
from fuelroute.services.geocoding import geocode
from fuelroute.services.places import normalize_city


class GeocodeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for name, state, lat, lon in [
            ("Chicago", "IL", 41.88, -87.63),
            ("St. Louis", "MO", 38.63, -90.20),
        ]:
            City.objects.create(
                name=name, state=state, search_key=normalize_city(name), latitude=lat, longitude=lon
            )

    def test_lat_lon_input(self):
        location, calls = geocode("41.88, -87.63")
        self.assertEqual((location.lat, location.lon, location.source, calls), (41.88, -87.63, "coordinates", 0))

    def test_city_state_code_uses_local_table(self):
        location, calls = geocode("Chicago, IL")
        self.assertEqual((location.source, calls), ("city", 0))

    def test_full_state_name_and_country_suffix(self):
        location, _ = geocode("chicago, Illinois, USA")
        self.assertEqual(location.label, "Chicago, IL")

    def test_saint_spelling_variants_match(self):
        location, _ = geocode("Saint Louis, MO")
        self.assertEqual(location.label, "St. Louis, MO")

    @patch("fuelroute.services.geocoding.requests.get")
    def test_non_us_state_is_rejected_without_external_call(self, mock_get):
        with self.assertRaises(InvalidLocationError):
            geocode("Toronto, ON")
        mock_get.assert_not_called()

    def test_coordinates_outside_usa_are_rejected(self):
        with self.assertRaises(InvalidLocationError):
            geocode("51.5, -0.12")  # London

    def test_empty_input_is_rejected(self):
        with self.assertRaises(InvalidLocationError):
            geocode("   ")

    @patch("fuelroute.services.geocoding.requests.get")
    def test_unknown_city_uses_structured_nominatim_search(self, mock_get):
        mock_get.return_value.json.return_value = []
        with self.assertRaises(InvalidLocationError):
            geocode("Narnia, TX")
        params = mock_get.call_args.kwargs["params"]
        self.assertEqual((params["city"], params["state"]), ("Narnia", "Texas"))
