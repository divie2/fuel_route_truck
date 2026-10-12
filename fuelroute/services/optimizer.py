"""Choose where to buy fuel and how much, minimizing total cost.

Classic greedy for a fixed route (optimal for this problem):
  At each station:
    1. If a cheaper station is within range, buy just enough to reach the nearest one.
    2. Else if the finish is within range, buy just enough to finish.
    3. Else fill the tank and drive to the cheapest station within range.

The truck starts at the first station (mile 0) with an empty tank.
Pure Python, no Django, so it's easy to unit test.
"""

from dataclasses import dataclass, field

from .exceptions import NoFeasiblePlanError

_EPSILON = 1e-9


@dataclass(frozen=True)
class StationOnRoute:
    key: int
    route_mile: float
    price: float


@dataclass
class Purchase:
    station: StationOnRoute
    gallons: float
    cost: float


@dataclass
class FuelPlan:
    purchases: list[Purchase] = field(default_factory=list)

    @property
    def total_gallons(self) -> float:
        return sum(p.gallons for p in self.purchases)

    @property
    def total_cost(self) -> float:
        return sum(p.cost for p in self.purchases)


def plan_fuel_stops(
    stations: list[StationOnRoute],
    total_miles: float,
    max_range_miles: float,
    miles_per_gallon: float,
) -> FuelPlan:
    route = sorted((s for s in stations if s.route_mile <= total_miles), key=lambda s: s.route_mile)
    if not route or route[0].route_mile > _EPSILON:
        raise NoFeasiblePlanError("No fuel station at the start of the route.")

    plan = FuelPlan()
    fuel = 0.0  # in miles of range
    i = 0

    def buy(station: StationOnRoute, miles: float) -> None:
        if miles <= _EPSILON:
            return
        gallons = miles / miles_per_gallon
        plan.purchases.append(Purchase(station, gallons, gallons * station.price))

    while True:
        here = route[i]
        cheaper = None
        cheapest_in_range = None

        k = i + 1
        while k < len(route) and route[k].route_mile - here.route_mile <= max_range_miles:
            if route[k].price < here.price:
                cheaper = k
                break
            # "<=" so ties prefer the farther station (fewer stops).
            if cheapest_in_range is None or route[k].price <= route[cheapest_in_range].price:
                cheapest_in_range = k
            k += 1

        to_finish = total_miles - here.route_mile

        if cheaper is not None:
            need = route[cheaper].route_mile - here.route_mile
            buy(here, need - fuel)
            fuel = max(fuel, need) - need
            i = cheaper
        elif to_finish <= max_range_miles:
            buy(here, to_finish - fuel)
            return plan
        elif cheapest_in_range is None:
            raise NoFeasiblePlanError(
                f"No fuel station within {max_range_miles:.0f} miles after "
                f"mile {here.route_mile:.0f} of the route."
            )
        else:
            buy(here, max_range_miles - fuel)
            fuel = max_range_miles - (route[cheapest_in_range].route_mile - here.route_mile)
            i = cheapest_in_range
