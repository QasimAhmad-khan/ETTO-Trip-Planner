LINK:https://etto-trip-planner.vercel.app/
# ETTO Trip Planner

FMCSA HOS-Compliant Route & ELD Logbook Generator for property-carrying truck drivers.

## What it does

Enter a current location, pickup, and dropoff — the app calculates an HOS-compliant driving schedule and generates filled DOT Driver's Daily Log sheets.

**Outputs:**
- Interactive route map with color-coded stop markers (start, pickup, dropoff, fuel, break, restart)
- Multiple ELD log sheets covering the full trip, each with a 24-hour duty-status grid
- Fuel Route Optimizer tab: a US route map, cost-aware fuel stops, gallons purchased and total fuel spending

### Fuel route API

`POST /api/fuel/route` accepts two US locations and optional fuel already in the tank:

```json
{"start":"Dallas, TX","finish":"Denver, CO","starting_fuel_gallons":50}
```

The response includes `map_geojson`, `fuel_stops`, `total_money_spent_on_fuel_usd`,
`fuel_consumed_gallons`, and `distance_miles`. It assumes 500 miles of range and
10 MPG. The total is **fuel purchased during the trip**, excluding the value of
fuel already in the tank. A full tank is the default. The fixed route is chosen
by OpenRouteService, then fuel purchases on that route are optimized by choosing
the first cheaper reachable station, or filling when none is reachable. The
endpoint makes at most two geocoding calls and one directions call on a cold
request; no network calls are made for stations. Django's local cache reduces
repeat calls within a warm server process.

The supplied OPIS CSV did not contain station coordinates. The checked-in
`backend/trips/data/fuel_stations.json` is a compact snapshot of 6,598 US stations
resolved to **city centroids** using GeoNames. Stops and prices are estimates;
the optimizer assumes a fixed route and excludes detour miles and their fuel.
Where a location cannot be resolved in the US, routing fails, or station spacing
exceeds tank range, the API returns an error instead of an impossible plan.

**HOS rules enforced (70-hr / 8-day cycle):**
- 11-hour drive limit per shift
- 14-hour on-duty window
- 30-minute break after 8 cumulative hours of driving
- 10-hour off-duty reset
- 34-hour restart when cycle is exhausted
- Fuel stop every 1,000 miles
- 1 hour each for pickup and dropoff

## Stack

- **Backend:** Django 6.1.2 + Django REST Framework — HOS simulation engine, geocoding & routing via OpenRouteService
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

The deployed ETTO backend uses its existing `ORS_GEOCODE_API_KEY` and
`ORS_DIRECTIONS_API_KEY` for this endpoint too. The React frontend calls `/api`
on the same origin in production.

## Assumptions

- Property-carrying driver, 70-hr / 8-day cycle
- No adverse driving conditions
- Average speed: 55 mph
- Fuel every 1,000 miles (0.5 hr stop)
- 1 hour at pickup, 1 hour at dropoff
- Trip starts at current time (UTC) unless overridden
