from django.db import models


class City(models.Model):
    """A US city with coordinates, used for offline geocoding."""

    name = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    search_key = models.CharField(
        max_length=100, help_text="Normalized city name used for lookups."
    )
    latitude = models.FloatField()
    longitude = models.FloatField()

    class Meta:
        verbose_name_plural = "cities"
        constraints = [
            models.UniqueConstraint(
                fields=["search_key", "state"], name="unique_city_per_state"
            )
        ]

    def __str__(self) -> str:
        return f"{self.name}, {self.state}"


class FuelStation(models.Model):
    """A truck stop from the provided price list, placed at its city's coordinates."""

    opis_id = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=200)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2, db_index=True)
    rack_id = models.PositiveIntegerField(null=True, blank=True)
    price = models.DecimalField(
        max_digits=9, decimal_places=6, help_text="Retail price per gallon (USD)."
    )
    latitude = models.FloatField()
    longitude = models.FloatField()

    class Meta:
        ordering = ["price"]

    def __str__(self) -> str:
        return f"{self.name} ({self.city}, {self.state}) ${self.price}"
