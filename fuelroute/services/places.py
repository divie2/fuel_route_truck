"""Place-name helpers shared by data loading and geocoding."""

import re

US_STATES: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine",
    "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
    "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island",
    "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
    "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}

STATE_NAME_TO_CODE: dict[str, str] = {name.lower(): code for code, name in US_STATES.items()}

# Station cities missing from data/us_cities.csv: (city, state) -> (lat, lon).
MANUAL_CITY_COORDS: dict[tuple[str, str], tuple[float, float]] = {
    ("Port Wentworth", "GA"): (32.1488, -81.1632),
    ("Evergreen", "AL"): (31.4335, -86.9569),
    ("Henrico", "VA"): (37.5059, -77.3328),
    ("Elizabethport", "NJ"): (40.6476, -74.1960),
    ("University Park", "IL"): (41.4428, -87.6837),
}

_WORD_ALIASES = [
    (re.compile(r"\bsaint\b"), "st"),
    (re.compile(r"\bfort\b"), "ft"),
    (re.compile(r"\bmount\b"), "mt"),
]


def normalize_city(name: str) -> str:
    """Normalize a city name so "St. Louis", "Saint Louis" and "ST LOUIS" match."""
    key = name.strip().lower().replace(".", "").replace("-", " ").replace("'", "")
    for pattern, replacement in _WORD_ALIASES:
        key = pattern.sub(replacement, key)
    return re.sub(r"\s+", "", key)


def to_state_code(value: str) -> str | None:
    """Return the 2-letter state code for "TX" or "Texas", or None if not a US state."""
    value = value.strip()
    if value.upper() in US_STATES:
        return value.upper()
    return STATE_NAME_TO_CODE.get(value.lower())
