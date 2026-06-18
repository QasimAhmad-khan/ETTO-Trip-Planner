# ETTO Trip Planner

FMCSA HOS-Compliant Route & ELD Logbook Generator for property-carrying truck drivers.

## What it does

Enter a current location, pickup, and dropoff — the app calculates an HOS-compliant driving schedule and generates filled DOT Driver's Daily Log sheets.

**Outputs:**
- Interactive route map with color-coded stop markers (start, pickup, dropoff, fuel, break, restart)
- Multiple ELD log sheets covering the full trip, each with a 24-hour duty-status grid

**HOS rules enforced (70-hr / 8-day cycle):**
- 11-hour drive limit per shift
- 14-hour on-duty window
- 30-minute break after 8 cumulative hours of driving
- 10-hour off-duty reset
- 34-hour restart when cycle is exhausted
- Fuel stop every 1,000 miles
- 1 hour each for pickup and dropoff

## Stack

- **Backend:** Django 6 + Django REST Framework — HOS simulation engine, geocoding & routing via OpenRouteService
- **Frontend:** React 19 + Vite — Leaflet map, SVG ELD log sheets

## Setup

### Backend

```bash
cd backend
pip install -r requirements.txt
cp ../.env.example ../.env   # fill in your keys
python manage.py migrate
python manage.py runserver
```

### Frontend

```bash
cd frontend
npm install
cp ../.env.example .env.local   # set VITE_API_BASE_URL=http://localhost:8000
npm run dev
```

## Environment variables

See `.env.example`:

| Variable | Description |
|---|---|
| `ORS_GEOCODE_API_KEY` | OpenRouteService API key |
| `ORS_DIRECTIONS_API_KEY` | OpenRouteService API key (same key) |
| `SECRET_KEY` | Django secret key |
| `DEBUG` | `True` for local dev |
| `VITE_API_BASE_URL` | Backend URL for the frontend |

Get a free ORS key at [openrouteservice.org](https://openrouteservice.org/).

## Assumptions

- Property-carrying driver, 70-hr / 8-day cycle
- No adverse driving conditions
- Average speed: 55 mph
- Fuel every 1,000 miles (0.5 hr stop)
- 1 hour at pickup, 1 hour at dropoff
- Trip starts at current time (UTC) unless overridden
