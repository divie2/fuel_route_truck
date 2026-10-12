"""Turn user input ("lat,lon" or "City, ST") into coordinates.

Lookups use the local City table, so no external call is made in the common case.
Nominatim is only used as a fallback for inputs the local table can't resolve.
"""

import re
from dataclasses import dataclass

import requests
from django.conf import settings

from fuelroute.models import City

from .exceptions import InvalidLocationError
from .places import normalize_city, to_state_code

_LATLON_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")
_COUNTRY_SUFFIXES = {"usa", "us", "u.s.", "u.s.a.", "united states", "united states of america"}

# Rough bounding boxes (min_lat, max_lat, min_lon, max_lon) for the USA.
_US_BOXES = [
    (24.4, 49.5, -125.0, -66.9),  # contiguous states
    (51.0, 71.5, -180.0, -129.0),  # Alaska
    (18.9, 22.3, -160.3, -154.8),  # Hawaii
]


@dataclass(frozen=True)
class Location:
    query: str
    label: str
    lat: float
    lon: float
    source: str  # "coordinates" | "city" | "nominatim"

    def as_dict(self) -> dict:
        return {
            "query": self.query,
            "label": self.label,
            "lat": round(self.lat, 6),
            "lon": round(self.lon, 6),
            "source": self.source,
        }


def is_in_usa(lat: float, lon: float) -> bool:
    return any(a <= lat <= b and c <= lon <= d for a, b, c, d in _US_BOXES)


def geocode(query: str) -> tuple[Location, int]:
    """Resolve a location. Returns (location, number_of_external_api_calls)."""
    query = (query or "").strip()
    if not query:
        raise InvalidLocationError("Location must not be empty.")

    match = _LATLON_RE.match(query)
    if match:
        lat, lon = float(match.group(1)), float(match.group(2))
        if not is_in_usa(lat, lon):
            raise InvalidLocationError(f"Coordinates '{query}' are not within the USA.")
        return Location(query, f"{lat:.5f}, {lon:.5f}", lat, lon, "coordinates"), 0

    city = _lookup_city(query)
    if city is not None:
        return Location(query, str(city), city.latitude, city.longitude, "city"), 0

    return _geocode_nominatim(query), 1


def _lookup_city(query: str) -> City | None:
    parts = [p.strip() for p in query.split(",") if p.strip()]
    if parts and parts[-1].lower() in _COUNTRY_SUFFIXES:
        parts = parts[:-1]
    if len(parts) != 2:
        return None
    state = to_state_code(parts[1])
    if state is None:
        return None
    return City.objects.filter(search_key=normalize_city(parts[0]), state=state).first()


def _geocode_nominatim(query: str) -> Location:
    cfg = settings.FUEL_ROUTE
    try:
        response = requests.get(
            f"{cfg['NOMINATIM_URL']}/search",
            params={"q": query, "countrycodes": "us", "format": "jsonv2", "limit": 1},
            headers={"User-Agent": cfg["USER_AGENT"]},
            timeout=cfg["HTTP_TIMEOUT_SECONDS"],
        )
        response.raise_for_status()
        results = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise InvalidLocationError(
            f"Could not resolve '{query}'. Use 'City, ST' or 'lat,lon'."
        ) from exc

    if not results:
        raise InvalidLocationError(
            f"Could not find '{query}' in the USA. Use 'City, ST' or 'lat,lon'."
        )
    top = results[0]
    lat, lon = float(top["lat"]), float(top["lon"])
    if not is_in_usa(lat, lon):
        raise InvalidLocationError(f"'{query}' is not within the USA.")
    return Location(query, top.get("display_name", query), lat, lon, "nominatim")
