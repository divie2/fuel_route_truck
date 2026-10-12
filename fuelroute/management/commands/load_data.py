"""Load US cities and fuel stations into the database (run once, offline).

Usage:
    python manage.py load_data
"""

import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from fuelroute.models import City, FuelStation
from fuelroute.services.places import (
    MANUAL_CITY_COORDS,
    US_STATES,
    normalize_city,
)


class Command(BaseCommand):
    help = "Load US cities and fuel stations (geocoded from the cities file) into the database."

    def add_arguments(self, parser):
        cfg = settings.FUEL_ROUTE
        parser.add_argument("--stations", type=Path, default=cfg["STATIONS_CSV"])
        parser.add_argument("--cities", type=Path, default=cfg["CITIES_CSV"])

    def handle(self, *args, **options):
        stations_path: Path = options["stations"]
        cities_path: Path = options["cities"]
        for path in (stations_path, cities_path):
            if not path.exists():
                raise CommandError(f"File not found: {path}")

        cities = self._read_cities(cities_path)
        stations, stats = self._read_stations(stations_path, cities)

        with transaction.atomic():
            FuelStation.objects.all().delete()
            City.objects.all().delete()
            City.objects.bulk_create(cities.values(), batch_size=2000)
            FuelStation.objects.bulk_create(stations, batch_size=2000)

        self.stdout.write(self.style.SUCCESS(f"Loaded {len(cities)} cities."))
        self.stdout.write(
            self.style.SUCCESS(
                f"Loaded {len(stations)} fuel stations "
                f"({stats['rows']} CSV rows, {stats['duplicates']} duplicate rows merged, "
                f"{stats['non_us']} non-US rows skipped, "
                f"{stats['bad_price']} rows with invalid price skipped)."
            )
        )
        if stats["unmatched"]:
            self.stdout.write(
                self.style.WARNING(
                    f"{len(stats['unmatched'])} stations skipped (city not found): "
                    + ", ".join(sorted(stats["unmatched"]))
                )
            )

    def _read_cities(self, path: Path) -> dict[tuple[str, str], City]:
        """Return cities keyed by (normalized name, state). First occurrence wins."""
        cities: dict[tuple[str, str], City] = {}
        with path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                state = row["STATE_CODE"].strip()
                if state not in US_STATES:
                    continue
                name = row["CITY"].strip()
                key = (normalize_city(name), state)
                if key not in cities:
                    cities[key] = City(
                        name=name,
                        state=state,
                        search_key=key[0],
                        latitude=float(row["LATITUDE"]),
                        longitude=float(row["LONGITUDE"]),
                    )

        for (name, state), (lat, lon) in MANUAL_CITY_COORDS.items():
            key = (normalize_city(name), state)
            cities.setdefault(
                key,
                City(name=name, state=state, search_key=key[0], latitude=lat, longitude=lon),
            )
        return cities

    def _read_stations(
        self, path: Path, cities: dict[tuple[str, str], City]
    ) -> tuple[list[FuelStation], dict]:
        """Return one station per OPIS ID (lowest price), placed at its city's coordinates."""
        stats = {"rows": 0, "duplicates": 0, "non_us": 0, "bad_price": 0, "unmatched": set()}
        by_id: dict[int, FuelStation] = {}

        with path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                stats["rows"] += 1
                state = row["State"].strip()
                if state not in US_STATES:
                    stats["non_us"] += 1
                    continue

                try:
                    price = Decimal(row["Retail Price"].strip())
                except InvalidOperation:
                    stats["bad_price"] += 1
                    continue

                opis_id = int(row["OPIS Truckstop ID"])
                existing = by_id.get(opis_id)
                if existing is not None:
                    stats["duplicates"] += 1
                    if price < existing.price:
                        existing.price = price
                    continue

                city_name = row["City"].strip()
                city = cities.get((normalize_city(city_name), state))
                if city is None:
                    stats["unmatched"].add(f"{city_name}, {state}")
                    continue

                rack_id = row["Rack ID"].strip()
                by_id[opis_id] = FuelStation(
                    opis_id=opis_id,
                    name=row["Truckstop Name"].strip(),
                    address=row["Address"].strip(),
                    city=city_name,
                    state=state,
                    rack_id=int(rack_id) if rack_id.isdigit() else None,
                    price=price,
                    latitude=city.latitude,
                    longitude=city.longitude,
                )

        return list(by_id.values()), stats
