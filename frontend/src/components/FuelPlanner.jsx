import { useState } from 'react';
import { MapContainer, Marker, Polyline, Popup, TileLayer, useMap } from 'react-leaflet';
import L from 'leaflet';
import { useEffect } from 'react';
import { planFuelRoute } from '../lib/api';

function FitRoute({ coordinates }) {
  const map = useMap();
  useEffect(() => {
    if (coordinates.length > 1) map.fitBounds(L.latLngBounds(coordinates), { padding: [35, 35] });
  }, [coordinates, map]);
  return null;
}

const icon = (color) => L.divIcon({
  html: `<span style="display:block;width:18px;height:18px;border:3px solid white;border-radius:50%;background:${color};box-shadow:0 1px 5px #3337"></span>`,
  className: '', iconSize: [18, 18], iconAnchor: [9, 9],
});
const startIcon = icon('#2F7D5B');
const finishIcon = icon('#1F4E66');
const fuelIcon = icon('#B07A2E');

export default function FuelPlanner() {
  const [start, setStart] = useState('');
  const [finish, setFinish] = useState('');
  const [startingFuel, setStartingFuel] = useState('50');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setError('');
    setLoading(true);
    try {
      setResult(await planFuelRoute({
        start: start.trim(), finish: finish.trim(), starting_fuel_gallons: Number(startingFuel),
      }));
    } catch (failure) {
      setResult(null);
      setError(failure.message);
    } finally {
      setLoading(false);
    }
  }

  const route = result?.map_geojson?.features?.find((feature) => feature.properties.kind === 'route');
  const coordinates = route ? route.geometry.coordinates.map(([lon, lat]) => [lat, lon]) : [];
  const stops = result?.fuel_stops || [];

  return (
    <div className="layout-grid">
      <div className="sidebar">
        <div className="form-card">
          <div className="form-card-header"><h2>Fuel Route Optimizer</h2></div>
          <form className="form-card-body" onSubmit={submit}>
            <p className="fuel-intro">Find lower priced fuel stops along a US driving route. Uses a 500 mile tank range and 10 MPG.</p>
            <label className="field-group"><span className="field-label">Start in the USA</span>
              <input type="text" value={start} onChange={(event) => setStart(event.target.value)} placeholder="Dallas, TX" minLength={2} required /></label>
            <label className="field-group"><span className="field-label">Finish in the USA</span>
              <input type="text" value={finish} onChange={(event) => setFinish(event.target.value)} placeholder="Denver, CO" minLength={2} required /></label>
            <label className="field-group"><span className="field-label">Fuel already in tank (gallons)</span>
              <input type="number" value={startingFuel} onChange={(event) => setStartingFuel(event.target.value)} min="0" max="50" step="0.1" required /></label>
            {error && <div className="error-banner" role="alert">{error}</div>}
            <button className="primary" disabled={loading}>{loading ? 'Optimizing route…' : 'Find Fuel Stops →'}</button>
            <p className="fuel-note">The total counts fuel bought on the trip. Fuel already in the tank is excluded.</p>
          </form>
        </div>
      </div>
      <div>
        {result ? <>
          <div className="fuel-metrics">
            <div className="surface fuel-metric"><span>Route distance</span><strong>{result.distance_miles.toLocaleString()} mi</strong></div>
            <div className="surface fuel-metric"><span>Fuel stops</span><strong>{stops.length}</strong></div>
            <div className="surface fuel-metric"><span>Fuel purchased</span><strong>${result.total_money_spent_on_fuel_usd}</strong></div>
          </div>
          <p className="section-label">Optimized Route Map</p>
          <div className="map-wrap">
            <MapContainer center={[39.8283, -98.5795]} zoom={4} style={{ height: '100%', width: '100%' }}>
              <TileLayer attribution='Map data: <a href="https://www.usgs.gov/">USGS</a>'
                url="https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}" maxZoom={16} />
              <FitRoute coordinates={coordinates} />
              <Polyline positions={coordinates} color="#1F4E66" weight={5} />
              <Marker position={[result.start.coordinates[1], result.start.coordinates[0]]} icon={startIcon}>
                <Popup>Start: {result.start.label}</Popup></Marker>
              <Marker position={[result.finish.coordinates[1], result.finish.coordinates[0]]} icon={finishIcon}>
                <Popup>Finish: {result.finish.label}</Popup></Marker>
              {stops.map((stop) => <Marker key={stop.station_id} position={[stop.coordinates[1], stop.coordinates[0]]} icon={fuelIcon}>
                <Popup><strong>{stop.name}</strong><br />{stop.city}, {stop.state}<br />${Number(stop.price_per_gallon_usd).toFixed(3)}/gal · {stop.gallons} gal</Popup>
              </Marker>)}
            </MapContainer>
          </div>
          <p className="section-label">Recommended Fuel Purchases</p>
          <div className="surface fuel-list">
            {stops.length ? stops.map((stop, index) => <div className="fuel-stop" key={stop.station_id}>
              <span className="fuel-stop-number">{index + 1}</span>
              <div><strong>{stop.name}</strong><div>{stop.city}, {stop.state} · mile {stop.mile_marker}</div>
                <small>{stop.address} · approx. {stop.distance_from_route_miles} mi from route</small></div>
              <div className="fuel-stop-cost"><strong>${stop.cost_usd}</strong><div>{stop.gallons} gal @ ${Number(stop.price_per_gallon_usd).toFixed(3)}</div></div>
            </div>) : <p>No purchase is needed with the selected starting fuel.</p>}
          </div>
          <p className="fuel-note">{result.pricing_note}</p>
        </> : !loading && <div className="fuel-empty">Enter your route to see priced fuel stops and total spending.</div>}
        {loading && <div className="fuel-empty">Finding the route and lowest cost stops…</div>}
      </div>
    </div>
  );
}
