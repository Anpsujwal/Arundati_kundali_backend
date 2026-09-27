"""
Pydantic models for the Arundhati Astrology Service.

These define the request/response contract between
the Node.js backend (Kundali provider) and this Python service.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ─── Request ─────────────────────────────────────────────────────────────────

class BirthDetails(BaseModel):
    """Input required to generate a Kundali."""

    date_of_birth: str = Field(
        ...,
        description="ISO date string, e.g. '1990-06-15'",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    birth_time: str = Field(
        ...,
        description="HH:MM (24-hour), e.g. '08:30'",
        pattern=r"^\d{2}:\d{2}$",
    )
    birth_place: str = Field(..., description="Human-readable place name")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    timezone: str = Field(..., description="IANA timezone, e.g. 'Asia/Kolkata'")


# ─── Response sub-models ──────────────────────────────────────────────────────

class PlanetPosition(BaseModel):
    planet: str
    sign: str
    house: int
    degree: float
    nakshatra: str
    nakshatra_pada: int


class HouseInfo(BaseModel):
    house: int
    sign: str
    lord: str


class ChartCore(BaseModel):
    lagna: str          # Ascendant sign name
    rashi: str          # Moon sign name
    nakshatra: str      # Moon nakshatra
    nakshatra_pada: int # 1–4


class CalculationMeta(BaseModel):
    provider: str = "pyjhora"
    provider_version: str
    ayanamsa: str
    house_system: str
    generated_at: str   # ISO 8601 UTC timestamp


# ─── Top-level response ───────────────────────────────────────────────────────

class StandardKundali(BaseModel):
    """
    Provider-neutral Kundali object.
    The Node.js backend stores and operates on this structure only.
    Never depend on PyJHora internals beyond this boundary.
    """
    birth: BirthDetails
    chart: ChartCore
    planets: list[PlanetPosition]
    houses: list[HouseInfo]
    meta: CalculationMeta


class ErrorResponse(BaseModel):
    error: str
    code: str
    detail: Optional[str] = None
