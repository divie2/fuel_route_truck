# Fuel Route Planner API

A Django REST API that takes a start and finish location in the USA, then returns:

- the driving route, as GeoJSON and as an interactive map,
- the most cost-effective fuel stops along the route (500-mile range, 10 mpg),
- the total fuel cost for the trip.

It makes **one call to an external routing API per request**, and **zero** for repeat trips, which are served from the cache.

---

## Quick start

Requires Python 3.12+.

```bash
git clone <this-repo-url> fuel-route && cd fuel-route

python -m venv .venv
source .venv/bin/activate          # Windows (Git Bash): source .venv/Scripts/activate
pip install -r requirements.txt

python manage.py migrate
python manage.py load_data         # imports cities + fuel stations (one-time, offline)
python manage.py runserver
```

Run the tests (no network needed; the routing API is mocked):

```bash
python manage.py test fuelroute
```

---

## API

### `POST /api/route/`

```bash
curl -X POST http://127.0.0.1:8000/api/route/ \
  -H "Content-Type: application/json" \
  -d '{"start": "Chicago, IL", "finish": "Los Angeles, CA"}'
```

`GET /api/route/?start=Chicago, IL&finish=Los Angeles, CA` works too, which is handy in a browser.

**Location formats:** `"City, ST"`, `"City, State"`, or `"lat,lon"` (e.g. `"41.88,-87.63"`). Both locations must be in the USA.

**Response** for Chicago, IL → Los Angeles, CA (real output; the geometry, stop list and assumptions are shortened):

```json
{
  "start":  { "query": "Chicago, IL", "label": "Chicago, IL", "lat": 41.885847, "lon": -87.618123, "source": "city" },
  "finish": { "query": "Los Angeles, CA", "label": "Los Angeles, CA", "lat": 33.973093, "lon": -118.247896, "source": "city" },
  "route": {
    "distance_miles": 2024.4,
    "duration_hours": 35.58,
    "geometry": { "type": "LineString", "coordinates": [[-87.618113, 41.885513], "..."] }
  },
  "fuel_stops": [
    {
      "stop_number": 4,
      "opis_id": 68368,
      "name": "AKAL TRAVEL CENTER",
      "address": "I-80 EX 360",
      "city": "Waco",
      "state": "NE",
      "lat": 40.919826,
      "lon": -97.453352,
      "price_per_gallon": 2.799,
      "route_mile": 559.8,
      "distance_from_route_miles": 6.8,
      "gallons": 50.0,
      "cost": 139.95
    }
  ],
  "summary": {
    "total_distance_miles": 2024.4,
    "total_gallons": 202.4,
    "total_fuel_cost": 620.11,
    "number_of_stops": 7,
    "stations_considered": 253,
    "max_range_miles": 500,
    "miles_per_gallon": 10,
    "assumptions": ["..."]
  },
  "map_url": "http://127.0.0.1:8000/api/route/map/?start=Chicago%2C+IL&finish=Los+Angeles%2C+CA",
  "meta": { "routing_api_calls": 0, "geocoding_api_calls": 0, "route_cached": true, "elapsed_ms": 73.4 }
}
```

The `meta` block above is from a repeat request served from the cache. The first request for this route returned `"routing_api_calls": 1` and took about 2.7 s.

### `GET /api/route/map/?start=...&finish=...`

An HTML page (Leaflet with CARTO/OpenStreetMap tiles) that shows the route, the start and finish, and every fuel stop with its price, gallons and cost. Each JSON response includes this link as `map_url`. The map reuses the cached route, so opening it makes no extra routing call.

### Errors

| Status | `error.code` | When |
|---|---|---|
| 400 | (field errors) | `start` or `finish` is missing |
| 400 | `invalid_location` | Location not found, or not in the USA (e.g. `"Toronto, ON"`) |
| 422 | `no_feasible_fuel_plan` | No stations on the route, or a gap longer than 500 miles |
| 502 | `routing_failed` | The routing API is down or found no road route |

```json
{ "error": { "code": "invalid_location", "message": "'ON' is not a US state. Both locations must be within the USA." } }
```

---

## How it works

```
request ──> geocode start/finish ──> 1 routing call ──> stations near route ──> optimizer ──> response + map
            (local city table)       (OSRM, cached)     (KD-tree, in memory)    (dynamic programming)
```

1. **Geocoding (local, 0 API calls).** `"City, ST"` is looked up in a table of about 29,600 US cities loaded from a CSV. City names are normalized, so `St. Louis`, `Saint Louis` and `ST LOUIS` all match. Nominatim is used only as a fallback for unusual inputs.
2. **Routing (1 API call).** The [OSRM](https://project-osrm.org/) public server returns the road distance, the duration and the full route geometry. Results are cached by coordinates, so repeat requests and the map page make **0** calls.
3. **Stations near the route.** All 6,626 stations are held in memory as numpy arrays. The route is densified to one point every 0.5 miles and put into a scipy `cKDTree`. A single vectorized query then finds every station within **10 miles** of the route and its mile marker along the route. This takes milliseconds.
4. **Optimizer.** A dynamic program over (station, fuel in tank) picks where to stop and how much to buy, minimizing total fuel cost. It adds a small $5 penalty per stop when choosing stops (the penalty isn't part of the reported cost). Without it, the mathematically cheapest plan made 19 stops between Chicago and LA, some buying 0.03 gallons to save a few cents. With it, the plan makes 7 real fill-ups for $5.92 more. The penalty is configurable (`STOP_PENALTY_USD`; set it to `0` for the pure lowest-cost plan).

### Performance

- Cold request (first time a route is seen): dominated by the single OSRM call, about 2.7 s for Chicago → Los Angeles.
- Cached request: no external calls, 73 ms for the same 2,024-mile route.
- `meta.elapsed_ms`, `meta.routing_api_calls` and `meta.route_cached` are returned with every response, so you can verify both.

---

## Data preparation

`python manage.py load_data` runs once, offline:

- **Fuel prices** (`data/fuel-prices-for-be-assessment.csv`, provided): 8,151 rows → **6,626 US stations**.
  - Rows for Canadian provinces (620) are skipped, because the API is USA-only.
  - Some stations appear more than once with different prices (905 duplicate rows). The **lowest** price per OPIS ID is kept.
- **Coordinates.** The price list has addresses but no latitude/longitude, and coordinates are needed to know which stations lie along a route. Each station is placed at its city's coordinates from `data/us_cities.csv`, which matches 99.8% of stations. The remaining 5 cities are covered by a small manual table in `fuelroute/services/places.py`. Geocoding all 6,626 addresses through an API would take hours, because free APIs are rate-limited, and highway-exit addresses like `I-44, EXIT 283` often don't geocode at all.

## Assumptions

- Vehicle range is 500 miles at 10 mpg.
- The truck starts with an empty tank and first fills up at the first station on the route, so the total cost covers the whole trip.
- Only stations within 10 miles of the route are considered, and detour distance isn't costed.
- Stations are positioned at their city's centre (accurate to a few miles), which is fine within a 10-mile corridor.
- The lowest listed price is used for stations with several prices.

## Configuration

All tunables are in `config/settings.py` under `FUEL_ROUTE`:

| Setting | Default |
|---|---|
| `MAX_RANGE_MILES` | 500 |
| `MILES_PER_GALLON` | 10 |
| `CORRIDOR_MILES` | 10 |
| `STOP_PENALTY_USD` | 5.0 |
| `OSRM_URL` | `https://router.project-osrm.org` (env `OSRM_URL`) |

Use the environment variables `DJANGO_SECRET_KEY`, `DJANGO_DEBUG` and `DJANGO_ALLOWED_HOSTS` for anything beyond local use.

## Project structure

```
config/                       Django settings and root URLs
fuelroute/
  models.py                   FuelStation, City
  management/commands/
    load_data.py              CSV import + offline geocoding
  services/
    places.py                 name normalization, US states, manual coordinates
    geocoding.py              "City, ST" / "lat,lon" -> coordinates
    routing.py                OSRM client + cache
    station_index.py          in-memory stations, KD-tree corridor search
    optimizer.py              fuel stop dynamic program (pure, unit-tested)
    planner.py                orchestrates everything, builds the response
  views.py, serializers.py    API endpoint + map page
  templates/fuelroute/map.html
  tests/                      25 tests (optimizer, geocoding, station index, API)
data/                         fuel prices, US cities (+ license)
```

## Possible improvements

- Use the real coordinates of each truck stop instead of the city centre, by geocoding the stations once with a paid geocoder.
- Cost the detour distance from the route to each station.
- Use a shared cache (Redis) and a self-hosted OSRM instance in production. The public OSRM demo server has no uptime guarantee.

## Credits

- Routing: [OSRM](https://project-osrm.org/) public API, built on © OpenStreetMap contributors.
- Map tiles: © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors, © [CARTO](https://carto.com/attributions), rendered with [Leaflet](https://leafletjs.com/).
- City coordinates: [kelvins/US-Cities-Database](https://github.com/kelvins/US-Cities-Database) (MIT, see `data/LICENSE-us_cities.txt`).
- Fuel prices: provided by Spotter for this assessment.
