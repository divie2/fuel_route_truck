"""Driving route from the free OSRM API (one call per start/finish pair, then cached)."""

from dataclasses import dataclass

import requests
from django.conf import settings
from django.core.cache import cache

from .exceptions import RoutingError
from .geocoding import Location

METERS_PER_MILE = 1609.344


@dataclass(frozen=True)
class Route:
    distance_miles: float
    duration_seconds: float
    coordinates: list[list[float]]  # GeoJSON order: [lon, lat]


def get_route(start: Location, finish: Location) -> tuple[Route, bool]:
    """Return (route, served_from_cache)."""
    key = f"osrm:{start.lat:.5f},{start.lon:.5f}:{finish.lat:.5f},{finish.lon:.5f}"
    cached = cache.get(key)
    if cached is not None:
        return cached, True

    route = _fetch_route(start, finish)
    cache.set(key, route)
    return route, False


def _fetch_route(start: Location, finish: Location) -> Route:
    cfg = settings.FUEL_ROUTE
    url = (
        f"{cfg['OSRM_URL']}/route/v1/driving/"
        f"{start.lon},{start.lat};{finish.lon},{finish.lat}"
    )
    try:
        response = requests.get(
            url,
            params={"overview": "full", "geometries": "geojson"},
            headers={"User-Agent": cfg["USER_AGENT"]},
            timeout=cfg["HTTP_TIMEOUT_SECONDS"],
        )
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise RoutingError(f"Routing service unavailable: {exc}") from exc

    if data.get("code") != "Ok" or not data.get("routes"):
        message = data.get("message") or data.get("code") or "unknown error"
        raise RoutingError(f"No driving route found: {message}")

    best = data["routes"][0]
    return Route(
        distance_miles=best["distance"] / METERS_PER_MILE,
        duration_seconds=best["duration"],
        coordinates=best["geometry"]["coordinates"],
    )
