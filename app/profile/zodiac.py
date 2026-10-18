"""Stubbed astrology.

Sun sign from a date-range lookup. The brief explicitly says a real
computation engine is out of scope — the point is using profile data in the
conversation, not calculating charts.

Trade-off: cusp dates are fixed here, where a real ephemeris would shift them
by up to a day depending on year and birth time. Swapping in `pyswisseph`
means replacing this one function; nothing above it changes.
"""
from datetime import date

# (first month, first day, sign) — tropical western sun-sign ranges, in order.
_RANGES: tuple[tuple[int, int, str], ...] = (
    (1, 20, "Aquarius"),
    (2, 19, "Pisces"),
    (3, 21, "Aries"),
    (4, 20, "Taurus"),
    (5, 21, "Gemini"),
    (6, 21, "Cancer"),
    (7, 23, "Leo"),
    (8, 23, "Virgo"),
    (9, 23, "Libra"),
    (10, 23, "Scorpio"),
    (11, 22, "Sagittarius"),
    (12, 22, "Capricorn"),
)

_ELEMENTS: dict[str, str] = {
    "Aries": "fire", "Leo": "fire", "Sagittarius": "fire",
    "Taurus": "earth", "Virgo": "earth", "Capricorn": "earth",
    "Gemini": "air", "Libra": "air", "Aquarius": "air",
    "Cancer": "water", "Scorpio": "water", "Pisces": "water",
}

# One short, neutral line per sign. Enough to colour a reply without
# pretending to be a chart reading.
_TRAITS: dict[str, str] = {
    "Aries": "direct, fast to start, impatient with slow processes",
    "Taurus": "steady, values security, resists rushed change",
    "Gemini": "curious, verbal, juggles several threads at once",
    "Cancer": "protective, led by comfort and people close by",
    "Leo": "confident, wants visible work and recognition",
    "Virgo": "analytical, detail-driven, hard on their own output",
    "Libra": "weighs options carefully, dislikes one-sided decisions",
    "Scorpio": "intense, researches deeply before committing",
    "Sagittarius": "optimistic, drawn to scope and new ground",
    "Capricorn": "disciplined, long-horizon, status-aware",
    "Aquarius": "independent, systems-minded, contrarian by instinct",
    "Pisces": "intuitive, people-led, needs meaning in the work",
}


def sun_sign(dob: date) -> str:
    """Sun sign for a date of birth. Late December falls back to Capricorn."""
    sign = "Capricorn"  # 22 Dec - 19 Jan wraps the year, so it is the default
    for month, day, name in _RANGES:
        if (dob.month, dob.day) >= (month, day):
            sign = name
    return sign


def element(sign: str) -> str | None:
    return _ELEMENTS.get(sign)


def traits(sign: str) -> str | None:
    return _TRAITS.get(sign)


def describe(dob: date | None) -> dict[str, str]:
    """Everything the prompt layer needs, or an empty dict when DOB is missing."""
    if dob is None:
        return {}
    sign = sun_sign(dob)
    return {"zodiac": sign, "element": _ELEMENTS[sign], "traits": _TRAITS[sign]}
