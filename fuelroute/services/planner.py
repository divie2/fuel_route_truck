"""Orchestrates geocoding -> route -> nearby stations -> fuel plan -> response data."""

import math
import time
from dataclasses import replace

from django.conf import settings

from fuelroute.models import FuelStation

from .exceptions import NoFeasiblePlanError
from .geocoding import geocode
from .optimizer import StationOnRoute, plan_fuel_stops
from .routing import get_route
from .station_index import densify_route, find_stations_near_route

MAX_GEOMETRY_POINTS = 1500

ASSUMPTIONS = [
    "Vehicle range is {max_range} miles and it achieves {mpg} miles per gallon.",
    "The truck starts with an empty tank and first fills up at the first station on the route.",
    "Only stations within {corridor} miles of the route are considered; detours are not costed.",
    "Stations are placed at their city's centre (the price list has no coordinates).",
    "When a station has several prices in the list, the lowest is used.",
    "A stop is only added if it saves more than ${stop_penalty:.2f} (avoids tiny top-ups).",
]


def plan_trip(start_query: str, finish_query: str) -> dict:
    started = time.perf_counter()
    cfg = settings.FUEL_ROUTE
    max_range, mpg, corridor = cfg["MAX_RANGE_MILES"], cfg["MILES_PER_GALLON"], cfg["CORRIDOR_MILES"]

    start, start_calls = geocode(start_query)
    finish, finish_calls = geocode(finish_query)
    route, route_cached = get_route(start, finish)

    lats, lons, cum = densify_route(route.coordinates)
    if cum[-1] > 0:
        cum = cum * (route.distance_miles / cum[-1])  # align with the road distance
    nearby = find_stations_near_route(lats, lons, cum, corridor)
    if not nearby:
        raise NoFeasiblePlanError("No fuel stations found along this route.")

    by_id = {s.opis_id: s for s in nearby}
    on_route = sorted(
        (StationOnRoute(s.opis_id, s.route_mile, s.price) for s in nearby),
        key=lambda s: s.route_mile,
    )
    # Empty tank at the start: treat the first station on the route as mile 0.
    on_route[0] = replace(on_route[0], route_mile=0.0)

    plan = plan_fuel_stops(
        on_route, route.distance_miles, max_range, mpg, stop_penalty=cfg["STOP_PENALTY_USD"]
    )

    details = FuelStation.objects.in_bulk(
        [p.station.key for p in plan.purchases], field_name="opis_id"
    )
    stops = []
    for number, purchase in enumerate(plan.purchases, start=1):
        station = details[purchase.station.key]
        found = by_id[purchase.station.key]
        stops.append(
            {
                "stop_number": number,
                "opis_id": station.opis_id,
                "name": station.name,
                "address": station.address,
                "city": station.city,
                "state": station.state,
                "lat": station.latitude,
                "lon": station.longitude,
                "price_per_gallon": round(float(station.price), 3),
                "route_mile": round(found.route_mile, 1),
                "distance_from_route_miles": round(found.off_route_miles, 1),
                "gallons": round(purchase.gallons, 2),
                "cost": round(purchase.cost, 2),
            }
        )

    return {
        "start": start.as_dict(),
        "finish": finish.as_dict(),
        "route": {
            "distance_miles": round(route.distance_miles, 1),
            "duration_hours": round(route.duration_seconds / 3600, 2),
            "geometry": {
                "type": "LineString",
                "coordinates": simplify_coordinates(route.coordinates, MAX_GEOMETRY_POINTS),
            },
        },
        "fuel_stops": stops,
        "summary": {
            "total_distance_miles": round(route.distance_miles, 1),
            "total_gallons": round(plan.total_gallons, 2),
            "total_fuel_cost": round(plan.total_cost, 2),
            "number_of_stops": len(stops),
            "stations_considered": len(nearby),
            "max_range_miles": max_range,
            "miles_per_gallon": mpg,
            "assumptions": [
                a.format(
                    max_range=max_range,
                    mpg=mpg,
                    corridor=corridor,
                    stop_penalty=cfg["STOP_PENALTY_USD"],
                )
                for a in ASSUMPTIONS
            ],
        },
        "meta": {
            "routing_api_calls": 0 if route_cached else 1,
            "geocoding_api_calls": start_calls + finish_calls,
            "route_cached": route_cached,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        },
    }


def simplify_coordinates(coordinates: list[list[float]], max_points: int) -> list[list[float]]:
    """Keep every n-th point (plus the last) so the response stays small."""
    if len(coordinates) <= max_points:
        return coordinates
    step = math.ceil(len(coordinates) / max_points)
    simplified = coordinates[::step]
    if simplified[-1] != coordinates[-1]:
        simplified.append(coordinates[-1])
    return simplified
