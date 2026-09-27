"""
Arundhati Astrology Service — FastAPI application.

Internal microservice: called only by the Node.js backend.
NOT exposed to the public internet.

Responsibilities:
  - Accept birth details
  - Delegate to PyJHora via kundali_generator.py
  - Return a StandardKundali JSON object

Does NOT contain:
  - Authentication logic
  - Matrimonial business rules
  - Gotra filtering
  - Match ranking
  - Frontend concerns
"""

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from models import BirthDetails, StandardKundali, ErrorResponse
from kundali_generator import generate_kundali

# ─── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("astrology-service")


# ─── App lifespan ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Arundhati Astrology Service starting up.")
    yield
    logger.info("Arundhati Astrology Service shutting down.")


# ─── Application ─────────────────────────────────────────────────────────────

app = FastAPI(
    title="Arundhati Astrology Service",
    description=(
        "Internal Vedic astrology computation service.\n\n"
        "**Configuration**: Lahiri Ayanamsa · Whole Sign Houses · Sidereal.\n\n"
        "This service performs deterministic calculations only. "
        "It does NOT contain any AI, LLM, or interpretive logic."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ─── Exception handlers ───────────────────────────────────────────────────────

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    logger.warning("ValueError in request to %s: %s", request.url.path, str(exc))
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            error="INVALID_BIRTH_DATA",
            code="INVALID_BIRTH_DATA",
            detail=str(exc),
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error in request to %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="CALCULATION_FAILED",
            code="CALCULATION_FAILED",
            detail="An internal calculation error occurred.",  # sanitized — no stack trace
        ).model_dump(),
    )


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health", tags=["ops"])
def health():
    """Health check for orchestration and the Node.js backend."""
    return {"status": "ok", "service": "arundhati-astrology"}


@app.get("/geocode", tags=["utils"])
def geocode(place: str):
    """
    Convert a human-readable place name to lat/lng coordinates.
    Used by the Node.js backend to auto-fill coordinates from birth_place text.

    Returns: { place_name, latitude, longitude, found: bool }
    """
    from geopy.geocoders import Nominatim
    from geopy.exc import GeocoderTimedOut, GeocoderServiceError

    geolocator = Nominatim(user_agent="arundhati-matrimony-v1")
    try:
        location = geolocator.geocode(place, timeout=10)
    except (GeocoderTimedOut, GeocoderServiceError) as e:
        logger.warning("Geocoding failed for '%s': %s", place, e)
        raise HTTPException(status_code=503, detail="Geocoding service temporarily unavailable.")

    if not location:
        logger.info("Geocode: no result for '%s'", place)
        return {"place_name": place, "latitude": None, "longitude": None, "found": False}

    logger.info("Geocode: '%s' → (%.4f, %.4f)", place, location.latitude, location.longitude)
    return {
        "place_name": location.address,
        "latitude": location.latitude,
        "longitude": location.longitude,
        "found": True,
    }


@app.post(
    "/kundali/generate",
    response_model=StandardKundali,
    tags=["kundali"],
    summary="Generate a Kundali from birth details",
    responses={
        200: {"description": "Successfully generated Kundali"},
        422: {"model": ErrorResponse, "description": "Invalid birth data"},
        500: {"model": ErrorResponse, "description": "Calculation failure"},
    },
)
def generate(birth: BirthDetails) -> StandardKundali:
    """
    Generate a complete Vedic Kundali (birth chart) from the provided birth details.

    Configuration used:
    - **Ayanamsa**: Lahiri (Chithrapaksha) — sidereal
    - **House System**: Whole Sign (Parashari)
    - **Planets**: Sun, Moon, Mars, Mercury, Jupiter, Venus, Saturn, Rahu, Ketu

    The returned `StandardKundali` object is the canonical data contract
    between this service and the Node.js matchmaking engine.
    """
    logger.info(
        "Generating Kundali for %s %s (lat=%.4f, lng=%.4f, tz=%s)",
        birth.date_of_birth, birth.birth_time,
        birth.latitude, birth.longitude, birth.timezone,
    )
    kundali = generate_kundali(birth)
    logger.info(
        "Kundali generated: Lagna=%s, Rashi=%s, Nakshatra=%s Pada=%d",
        kundali.chart.lagna, kundali.chart.rashi,
        kundali.chart.nakshatra, kundali.chart.nakshatra_pada,
    )
    return kundali
