from django.test import SimpleTestCase

from fuelroute.services.exceptions import NoFeasiblePlanError
from fuelroute.services.optimizer import StationOnRoute as S
from fuelroute.services.optimizer import plan_fuel_stops


def plan(stations, total, penalty=0.0):
    return plan_fuel_stops(stations, total, max_range_miles=500, miles_per_gallon=10, stop_penalty=penalty)


class PlanFuelStopsTests(SimpleTestCase):
    def test_single_station_buys_exactly_the_fuel_needed(self):
        result = plan([S(1, 0, 3.0)], 300)
        self.assertEqual(len(result.purchases), 1)
        self.assertAlmostEqual(result.total_gallons, 30)
        self.assertAlmostEqual(result.total_cost, 90)

    def test_buys_only_enough_to_reach_a_cheaper_station(self):
        result = plan([S(1, 0, 4.0), S(2, 100, 3.0)], 400)
        self.assertEqual([p.station.key for p in result.purchases], [1, 2])
        self.assertAlmostEqual(result.purchases[0].gallons, 10)
        self.assertAlmostEqual(result.purchases[1].gallons, 30)
        self.assertAlmostEqual(result.total_cost, 130)

    def test_fills_up_when_the_next_station_is_more_expensive(self):
        result = plan([S(1, 0, 3.0), S(2, 400, 4.0)], 700)
        self.assertAlmostEqual(result.purchases[0].gallons, 50)  # full tank at the cheap one
        self.assertAlmostEqual(result.purchases[1].gallons, 20)
        self.assertAlmostEqual(result.total_cost, 230)

    def test_total_gallons_cover_the_whole_trip(self):
        stations = [S(i, i * 90, 3.0 + (i % 3) * 0.2) for i in range(30)]
        result = plan(stations, 2500)
        self.assertAlmostEqual(result.total_gallons, 250)

    def test_stop_penalty_skips_a_stop_that_saves_only_cents(self):
        stations = [S(1, 0, 3.00), S(2, 10, 2.99)]
        self.assertEqual(len(plan(stations, 300, penalty=0).purchases), 2)
        self.assertEqual(len(plan(stations, 300, penalty=5).purchases), 1)

    def test_stations_past_the_finish_are_ignored(self):
        result = plan([S(1, 0, 3.0), S(2, 900, 1.0)], 300)
        self.assertEqual([p.station.key for p in result.purchases], [1])

    def test_gap_longer_than_range_raises(self):
        with self.assertRaises(NoFeasiblePlanError):
            plan([S(1, 0, 3.0), S(2, 600, 3.0)], 700)

    def test_no_station_at_start_raises(self):
        with self.assertRaises(NoFeasiblePlanError):
            plan([S(1, 10, 3.0)], 300)
