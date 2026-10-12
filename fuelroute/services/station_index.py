"""Fast lookup of fuel stations close to a route.

Station coordinates are loaded from the database once and kept in memory as numpy
arrays. For each request we build a KD-tree on the (densified) route points and ask,
for every station, "how far is the nearest route point?". This takes milliseconds.
"""

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy.spatial import cKDTree

from fuelroute.models import FuelStation

EARTH_RADIUS_MILES = 3958.8


@dataclass(frozen=True)
class StationArrays:
    opis_ids: np.ndarray
    prices: np.ndarray
    xyz: np.ndarray  # unit vectors, shape (n, 3)


@dataclass(frozen=True)
class NearbyStation:
    opis_id: int
    price: float
    route_mile: float
    off_route_miles: float


@lru_cache(maxsize=1)
def get_station_arrays() -> StationArrays:
    rows = list(FuelStation.objects.values_list("opis_id", "price", "latitude", "longitude"))
    if not rows:
        return StationArrays(np.empty(0, int), np.empty(0), np.empty((0, 3)))
    ids, prices, lats, lons = zip(*rows)
    return StationArrays(
        opis_ids=np.array(ids, dtype=np.int64),
        prices=np.array(prices, dtype=float),
        xyz=to_unit_vectors(np.array(lats, dtype=float), np.array(lons, dtype=float)),
    )


def clear_station_cache() -> None:
    get_station_arrays.cache_clear()


def to_unit_vectors(lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
    lat, lon = np.radians(lats), np.radians(lons)
    return np.column_stack((np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)))


def haversine_miles(lat1, lon1, lat2, lon2) -> np.ndarray:
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = (
        np.sin((lat2 - lat1) / 2) ** 2
        + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(a))


def densify_route(
    coordinates: list[list[float]], max_step_miles: float = 0.5
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Add points so no two consecutive route points are more than max_step_miles apart.

    Returns (lats, lons, cumulative_miles).
    """
    coords = np.asarray(coordinates, dtype=float)
    lons, lats = coords[:, 0], coords[:, 1]
    if len(coords) < 2:
        return lats, lons, np.zeros(len(coords))

    seg_len = haversine_miles(lats[:-1], lons[:-1], lats[1:], lons[1:])
    steps = np.maximum(1, np.ceil(seg_len / max_step_miles)).astype(int)

    seg = np.repeat(np.arange(len(seg_len)), steps)
    first_of_seg = np.repeat(np.cumsum(steps) - steps, steps)
    t = (np.arange(steps.sum()) - first_of_seg) / steps[seg]

    out_lats = np.append(lats[seg] + (lats[seg + 1] - lats[seg]) * t, lats[-1])
    out_lons = np.append(lons[seg] + (lons[seg + 1] - lons[seg]) * t, lons[-1])
    seg_start_miles = np.concatenate(([0.0], np.cumsum(seg_len)))
    cum = np.append(seg_start_miles[seg] + seg_len[seg] * t, seg_start_miles[-1])
    return out_lats, out_lons, cum


def find_stations_near_route(
    lats: np.ndarray, lons: np.ndarray, cum_miles: np.ndarray, corridor_miles: float
) -> list[NearbyStation]:
    """Stations within corridor_miles of the route, with their position along it."""
    stations = get_station_arrays()
    if len(stations.opis_ids) == 0 or len(lats) == 0:
        return []

    tree = cKDTree(to_unit_vectors(lats, lons))
    max_chord = 2 * np.sin(corridor_miles / (2 * EARTH_RADIUS_MILES))
    chord, idx = tree.query(stations.xyz, distance_upper_bound=max_chord)

    hits = np.isfinite(chord)
    off_route = 2 * EARTH_RADIUS_MILES * np.arcsin(np.clip(chord[hits] / 2, 0, 1))
    route_miles = cum_miles[idx[hits]]

    return [
        NearbyStation(int(opis_id), float(price), float(mile), float(off))
        for opis_id, price, mile, off in zip(
            stations.opis_ids[hits], stations.prices[hits], route_miles, off_route
        )
    ]
