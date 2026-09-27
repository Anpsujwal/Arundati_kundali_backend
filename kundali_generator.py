"""
Kundali Generator — Swiss Ephemeris direct implementation.

This module is the ONLY place that imports Swiss Ephemeris.
All astrology calculations live here.
The rest of the application works with StandardKundali objects only.

Configuration (locked for consistency across all profiles):
  Ayanamsa   : Lahiri (most widely used in Vedic astrology, standard for North and South India)
  House System: Whole Sign (Parashari tradition used by Arundhati's Brahmin community)
  Calendar   : Sidereal (Vedic, NOT tropical)

DO NOT change these settings silently. Any change invalidates all stored Kundalis
and requires a full recalculation. Document the reason and bump provider_version.

Implementation note:
  pyjhora 4.8.7 is incompatible with pysweph >= 2.10.x because:
    1. The 'planets' submodule was removed from jhora.horoscope.chart
    2. swe.calc_ut() now returns a 3-tuple instead of 2-tuple, crashing jhora internals
  We bypass pyjhora entirely and call swisseph directly for all ephemeris calculations.
"""

from datetime import datetime, date
import importlib.metadata
from zoneinfo import ZoneInfo

import swisseph as swe

from models import (
    BirthDetails, StandardKundali, ChartCore,
    PlanetPosition, HouseInfo, CalculationMeta
)

# ─── Configuration constants ──────────────────────────────────────────────────

AYANAMSA_NAME = "Lahiri"
HOUSE_SYSTEM = "Whole Sign"

# Swiss Ephemeris ayanamsa mode for Lahiri
_SWE_AYANAMSA = swe.SIDM_LAHIRI

# Planet definitions: (display_name, swe_planet_id, is_ketu)
# Ketu = opposite node of Rahu (MEAN_NODE + 180°)
_PLANETS = [
    ("Sun",     swe.SUN,       False),
    ("Moon",    swe.MOON,      False),
    ("Mars",    swe.MARS,      False),
    ("Mercury", swe.MERCURY,   False),
    ("Jupiter", swe.JUPITER,   False),
    ("Venus",   swe.VENUS,     False),
    ("Saturn",  swe.SATURN,    False),
    ("Rahu",    swe.MEAN_NODE, False),
    ("Ketu",    swe.MEAN_NODE, True),   # South Node = Rahu + 180°
]

_SIGN_NAMES = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces"
]

_SIGN_LORDS = {
    "Aries": "Mars", "Taurus": "Venus", "Gemini": "Mercury",
    "Cancer": "Moon", "Leo": "Sun", "Virgo": "Mercury",
    "Libra": "Venus", "Scorpio": "Mars", "Sagittarius": "Jupiter",
    "Capricorn": "Saturn", "Aquarius": "Saturn", "Pisces": "Jupiter",
}

# 27 Nakshatras in order
_NAKSHATRAS = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishtha",
    "Shatabhisha", "Purva Bhadrapada", "Uttara Bhadrapada", "Revati",
]


def _get_provider_version() -> str:
    """Return installed swisseph package version string."""
    for pkg in ("pysweph", "pyswisseph", "pyjhora"):
        try:
            return f"{pkg}/{importlib.metadata.version(pkg)}"
        except importlib.metadata.PackageNotFoundError:
            continue
    return "swisseph/unknown"


def _sign_index_to_name(index: int) -> str:
    """Convert 0-based sign index to name. Handles wrapping."""
    return _SIGN_NAMES[int(index) % 12]


def _degree_to_nakshatra(absolute_degree: float) -> tuple[str, int]:
    """
    Convert an absolute ecliptic degree (0–360, sidereal) to Nakshatra and Pada.

    Each nakshatra spans 360/27 ≈ 13.333° and is divided into 4 padas of 3.333° each.
    Returns (nakshatra_name, pada) where pada is 1–4.
    """
    nak_span = 360.0 / 27.0     # 13.3333...°
    pada_span = nak_span / 4.0  # 3.3333...°

    nak_index = int(absolute_degree / nak_span) % 27
    remainder = absolute_degree % nak_span
    pada = int(remainder / pada_span) + 1
    pada = min(pada, 4)  # clamp to 4

    return _NAKSHATRAS[nak_index], pada


def _house_for_planet(planet_sign_index: int, lagna_sign_index: int) -> int:
    """
    Calculate house number (1–12) under Whole Sign system.
    House 1 = Lagna sign, House 2 = next sign, etc.
    """
    house = (planet_sign_index - lagna_sign_index) % 12 + 1
    return house


def _sidereal_longitude(jd_ut: float, swe_planet_id: int) -> float:
    """
    Compute sidereal longitude (Lahiri ayanamsa) for a planet.
    Returns degrees in [0, 360).

    Note: pysweph >= 2.10 returns a 3-tuple from swe.calc_ut();
    we always index [0] to get the positions tuple.
    """
    flags = swe.FLG_SIDEREAL | swe.FLG_SPEED
    result = swe.calc_ut(jd_ut, swe_planet_id, flags)
    pos = result[0]  # positions tuple: (lon, lat, dist, speed_lon, ...)
    return pos[0] % 360.0


def _compute_ascendant_sidereal(jd_ut: float, lat: float, lon: float) -> float:
    """
    Compute sidereal Lagna (Ascendant) using Lahiri ayanamsa.
    Returns degrees in [0, 360).
    """
    # swe.houses() returns (cusps_tuple, ascmc_tuple); ascmc[0] is tropical ASC
    _, ascmc = swe.houses(jd_ut, lat, lon, b'W')
    tropical_asc = ascmc[0]
    ayanamsa = swe.get_ayanamsa_ut(jd_ut)
    return (tropical_asc - ayanamsa) % 360.0


def generate_kundali(birth: BirthDetails) -> StandardKundali:
    """
    Generate a full Kundali from birth details using Swiss Ephemeris directly.

    Raises:
        ValueError: If birth data is malformed or ephemeris cannot compute.
        RuntimeError: If an unexpected library error occurs.
    """
    # ── Parse date/time ───────────────────────────────────────────────────────
    dob = date.fromisoformat(birth.date_of_birth)
    hour, minute = map(int, birth.birth_time.split(":"))

    # Convert local birth time to UT for Swiss Ephemeris
    tz = ZoneInfo(birth.timezone)
    local_dt = datetime(dob.year, dob.month, dob.day, hour, minute, tzinfo=tz)
    utc_offset_hours = local_dt.utcoffset().total_seconds() / 3600.0
    decimal_hour_local = hour + minute / 60.0
    decimal_hour_ut = decimal_hour_local - utc_offset_hours

    # ── Set ayanamsa (must be done before any swe calculations) ──────────────
    swe.set_sid_mode(_SWE_AYANAMSA)

    # ── Compute Julian Day (UT) ───────────────────────────────────────────────
    jd_ut = swe.julday(dob.year, dob.month, dob.day, decimal_hour_ut)

    # ── Lagna (Ascendant) ─────────────────────────────────────────────────────
    lagna_longitude = _compute_ascendant_sidereal(jd_ut, birth.latitude, birth.longitude)
    lagna_sign_index = int(lagna_longitude / 30) % 12
    lagna_name = _sign_index_to_name(lagna_sign_index)

    # ── Planetary positions ───────────────────────────────────────────────────
    planet_positions: list[PlanetPosition] = []
    moon_longitude: float = 0.0

    for name, swe_id, is_ketu in _PLANETS:
        lon = _sidereal_longitude(jd_ut, swe_id)
        if is_ketu:
            lon = (lon + 180.0) % 360.0  # Ketu = opposite of Rahu

        if name == "Moon":
            moon_longitude = lon

        sign_idx = int(lon / 30) % 12
        sign_name = _sign_index_to_name(sign_idx)
        house = _house_for_planet(sign_idx, lagna_sign_index)
        degree_in_sign = lon % 30
        p_nakshatra, p_pada = _degree_to_nakshatra(lon)

        planet_positions.append(PlanetPosition(
            planet=name,
            sign=sign_name,
            house=house,
            degree=round(degree_in_sign, 4),
            nakshatra=p_nakshatra,
            nakshatra_pada=p_pada,
        ))

    # ── Moon data (Rashi + Nakshatra) ─────────────────────────────────────────
    moon_sign_index = int(moon_longitude / 30) % 12
    rashi_name = _sign_index_to_name(moon_sign_index)
    nakshatra_name, nakshatra_pada = _degree_to_nakshatra(moon_longitude)

    # ── Houses (Whole Sign) ───────────────────────────────────────────────────
    houses: list[HouseInfo] = []
    for h in range(1, 13):
        sign_idx = (lagna_sign_index + h - 1) % 12
        sign_name = _sign_index_to_name(sign_idx)
        houses.append(HouseInfo(
            house=h,
            sign=sign_name,
            lord=_SIGN_LORDS[sign_name],
        ))

    # ── Assemble StandardKundali ──────────────────────────────────────────────
    return StandardKundali(
        birth=birth,
        chart=ChartCore(
            lagna=lagna_name,
            rashi=rashi_name,
            nakshatra=nakshatra_name,
            nakshatra_pada=nakshatra_pada,
        ),
        planets=planet_positions,
        houses=houses,
        meta=CalculationMeta(
            provider="swisseph-direct",
            provider_version=_get_provider_version(),
            ayanamsa=AYANAMSA_NAME,
            house_system=HOUSE_SYSTEM,
            generated_at=datetime.utcnow().isoformat() + "Z",
        ),
    )
