import numpy as np
from django.test import TestCase

from fuelroute.models import FuelStation
from fuelroute.services.station_index import (
    clear_station_cache,
    densify_route,
    find_stations_near_route,
    haversine_miles,
)


class DensifyRouteTests(TestCase):
    def test_points_are_at_most_the_max_step_apart(self):
        lats, lons, cum = densify_route([[-90.0, 40.0], [-90.0, 41.0]], max_step_miles=0.5)
        steps = haversine_miles(lats[:-1], lons[:-1], lats[1:], lons[1:])
        self.assertLessEqual(steps.max(), 0.5 + 1e-6)
        self.assertAlmostEqual(cum[-1], 69.1, delta=0.2)  # one degree of latitude
        self.assertTrue(np.all(np.diff(cum) >= 0))


class FindStationsNearRouteTests(TestCase):
    def setUp(self):
        clear_station_cache()
        self.addCleanup(clear_station_cache)
        for opis_id, lon_lat in [(1, (-90.0, 40.5)), (2, (-89.95, 40.5)), (3, (-85.0, 40.5))]:
            FuelStation.objects.create(
                opis_id=opis_id, name=f"S{opis_id}", address="", city="X", state="IL",
                price="3.000", longitude=lon_lat[0], latitude=lon_lat[1],
            )

    def test_only_stations_inside_the_corridor_are_returned(self):
        lats, lons, cum = densify_route([[-90.0, 40.0], [-90.0, 41.0]])
        found = {s.opis_id: s for s in find_stations_near_route(lats, lons, cum, corridor_miles=10)}

        self.assertEqual(set(found), {1, 2})  # station 3 is ~260 miles away
        # Distance is to the nearest densified route point (spaced <= 0.5 mi),
        # so a station on the route can be up to ~0.25 mi from that point.
        self.assertAlmostEqual(found[1].off_route_miles, 0, delta=0.3)
        self.assertAlmostEqual(found[2].off_route_miles, 2.6, delta=0.3)
        self.assertAlmostEqual(found[1].route_mile, 34.5, delta=0.5)  # halfway along
