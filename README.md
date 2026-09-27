# 🔮 Arundhati Astrology Service

Internal Python/FastAPI microservice that performs Vedic astrology calculations for the Arundhati Matrimony Platform.

## Architecture Role

```
Node.js Backend
      ↓ HTTP POST /kundali/generate
Astrology Service (this)
      ↓
PyJHora + Swiss Ephemeris
      ↓
StandardKundali JSON
```

This service is **internal only** — not exposed to the public internet.

## Configuration (locked)

| Setting | Value |
|---|---|
| Ayanamsa | Lahiri (Chithrapaksha) |
| House System | Whole Sign (Parashari) |
| Calendar | Sidereal |
| Planets | Sun, Moon, Mars, Mercury, Jupiter, Venus, Saturn, Rahu, Ketu |

> **Important**: Do not change these settings silently. Any change invalidates all stored Kundalis and requires a full recalculation.

## Setup

```bash
cd astrology-service
pip install -r requirements.txt
```

PyJHora depends on Swiss Ephemeris (`pyswisseph`). On Windows you may need Visual C++ build tools.

## Run

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

API docs available at: `http://localhost:8000/docs`

## Validate before use

```bash
python -m pytest tests/validation/known_cases.py -v
```

This runs the validation harness against known reference Kundalis. **All tests must pass** before using this service in production.

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/kundali/generate` | Generate a Kundali from birth details |

## Response: StandardKundali

```json
{
  "birth": { "date_of_birth": "...", "birth_time": "...", "..." },
  "chart": { "lagna": "Gemini", "rashi": "Scorpio", "nakshatra": "Anuradha", "nakshatra_pada": 2 },
  "planets": [{ "planet": "Sun", "sign": "...", "house": 1, "degree": 0.52, "nakshatra": "...", "nakshatra_pada": 3 }],
  "houses":  [{ "house": 1, "sign": "...", "lord": "..." }],
  "meta": { "provider": "pyjhora", "provider_version": "...", "ayanamsa": "Lahiri", "house_system": "Whole Sign", "generated_at": "..." }
}
```
