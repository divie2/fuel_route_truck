"""Choose where to buy fuel and how much, minimizing total cost.

Dynamic programming over (station, fuel in tank):
  - Distances are whole miles and fuel is measured in miles of range (0..max_range).
  - At each station you may buy any amount; buying costs gallons * price plus a
    fixed `stop_penalty`. The penalty avoids impractical plans with many tiny
    top-ups that save a few cents. It is not included in the reported cost.
  - Then you drive to the next station (or the finish) and the tank drops by the distance.

The truck starts at the first station (mile 0) with an empty tank.
Pure Python + numpy, no Django, so it's easy to unit test.
"""

from dataclasses import dataclass, field

import numpy as np

from .exceptions import NoFeasiblePlanError


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
    stop_penalty: float = 0.0,
) -> FuelPlan:
    finish = round(total_miles)
    capacity = int(max_range_miles)
    route = _cheapest_per_mile(stations, finish)
    if not route or route[0][0] != 0:
        raise NoFeasiblePlanError("No fuel station at the start of the route.")

    positions = [mile for mile, _ in route]
    hops = np.diff(positions + [finish])
    if hops.max(initial=0) > capacity:
        gap_at = positions[int(np.argmax(hops))]
        raise NoFeasiblePlanError(
            f"No fuel station within {capacity} miles after mile {gap_at} of the route."
        )

    levels = np.arange(capacity + 1)
    inf = np.inf
    arrive = np.full(capacity + 1, inf)
    arrive[0] = 0.0  # empty tank at the first station
    bought_from = []  # per station: fuel level before buying, or -1 if nothing bought

    for (_, station), hop in zip(route, hops):
        per_mile = station.price / miles_per_gallon
        # leave[g] = min(arrive[g], penalty + per_mile*g + min_{f<g}(arrive[f] - per_mile*f))
        shifted = arrive - per_mile * levels
        prefix_min = np.minimum.accumulate(shifted)
        prefix_arg = np.maximum.accumulate(np.where(shifted <= prefix_min, levels, 0))
        best_before = np.concatenate(([inf], prefix_min[:-1]))
        arg_before = np.concatenate(([-1], prefix_arg[:-1]))

        buy_cost = stop_penalty + per_mile * levels + best_before
        buy = buy_cost < arrive
        leave = np.where(buy, buy_cost, arrive)
        bought_from.append(np.where(buy, arg_before, -1))

        arrive = np.concatenate((leave[hop:], np.full(hop, inf)))

    end_level = int(np.argmin(arrive))
    if not np.isfinite(arrive[end_level]):
        raise NoFeasiblePlanError("No feasible fuel plan for this route.")

    # Walk backwards to recover the purchases.
    purchases = []
    level = end_level
    for (_, station), hop, source in zip(reversed(route), reversed(hops), reversed(bought_from)):
        level += int(hop)
        start_level = int(source[level])
        if start_level >= 0:
            gallons = (level - start_level) / miles_per_gallon
            purchases.append(Purchase(station, gallons, gallons * station.price))
            level = start_level
    purchases.reverse()
    return FuelPlan(purchases)


def _cheapest_per_mile(
    stations: list[StationOnRoute], finish: int
) -> list[tuple[int, StationOnRoute]]:
    """Round positions to whole miles and keep the cheapest station at each mile."""
    best: dict[int, StationOnRoute] = {}
    for station in stations:
        mile = round(station.route_mile)
        if mile > finish:
            continue
        if mile not in best or station.price < best[mile].price:
            best[mile] = station
    return sorted(best.items())
