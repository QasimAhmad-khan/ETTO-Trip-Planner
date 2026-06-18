import { useEffect, useState } from 'react';
import { MapContainer, TileLayer, Polyline, Marker, Popup, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';

// Fix Leaflet default icon (Vite asset-import issue)
import icon from 'leaflet/dist/images/marker-icon.png';
import iconShadow from 'leaflet/dist/images/marker-shadow.png';
const DefaultIcon = L.icon({ iconUrl: icon, shadowUrl: iconShadow, iconAnchor: [12, 41], popupAnchor: [1, -34] });
L.Marker.prototype.options.icon = DefaultIcon;

// Colour dots for each stop type
const STOP_COLORS = {
  start:   '#1F4E66',
  pickup:  '#2F7D5B',
  dropoff: '#B07A2E',
  fuel:    '#9AA0A6',
  break:   '#9AA0A6',
  reset:   '#3D4F7C',
  restart: '#D32F2F',
};

function makeIcon(color) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
    <circle cx="8" cy="8" r="7" fill="${color}" stroke="white" stroke-width="2"/>
  </svg>`;
  return L.divIcon({
    html: svg,
    className: '',
    iconSize: [16, 16],
    iconAnchor: [8, 8],
    popupAnchor: [0, -10],
  });
}

function decodePolyline(encoded) {
  if (!encoded) return [];
  const points = [];
  let index = 0, lat = 0, lng = 0;
  while (index < encoded.length) {
    let b, shift = 0, result = 0;
    do {
      b = encoded.charCodeAt(index++) - 63;
      result |= (b & 0x1f) << shift;
      shift += 5;
    } while (b >= 0x20);
    lat += (result & 1) ? ~(result >> 1) : (result >> 1);
    shift = 0; result = 0;
    do {
      b = encoded.charCodeAt(index++) - 63;
      result |= (b & 0x1f) << shift;
      shift += 5;
    } while (b >= 0x20);
    lng += (result & 1) ? ~(result >> 1) : (result >> 1);
    points.push([lat / 1e5, lng / 1e5]);
  }
  return points;
}

function BoundsFitter({ points }) {
  const map = useMap();
  useEffect(() => {
    if (points && points.length > 0) {
      map.fitBounds(L.latLngBounds(points), { padding: [50, 50] });
    }
  }, [points, map]);
  return null;
}

function formatDuration(hrs) {
  if (!hrs) return '';
  const h = Math.floor(hrs);
  const m = Math.round((hrs - h) * 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

export default function RouteMap({ route, stops }) {
  const [allPoints, setAllPoints] = useState([]);

  useEffect(() => {
    if (route?.geometry) {
      let pts = [];
      route.geometry.forEach(geom => { pts = pts.concat(decodePolyline(geom)); });
      setAllPoints(pts);
    }
  }, [route]);

  const defaultCenter = [39.8283, -98.5795];
  const mappableStops = (stops || []).filter(s => s.lat != null && s.lng != null);
  const boundsPoints = allPoints.length > 0 ? allPoints : mappableStops.map(s => [s.lat, s.lng]);

  return (
    <div className="map-wrap">
      <MapContainer center={defaultCenter} zoom={4} style={{ height: '100%', width: '100%' }}>
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />

        {boundsPoints.length > 0 && <BoundsFitter points={boundsPoints} />}

        {allPoints.length > 0 && (
          <Polyline positions={allPoints} color="#1F4E66" weight={4} opacity={0.8} />
        )}

        {mappableStops.map((stop, i) => (
          <Marker key={i} position={[stop.lat, stop.lng]} icon={makeIcon(STOP_COLORS[stop.type] || '#1F4E66')}>
            <Popup>
              <div style={{ fontFamily: 'sans-serif', fontSize: '13px', minWidth: '160px' }}>
                <strong style={{ textTransform: 'uppercase', fontSize: '11px', letterSpacing: '0.05em' }}>
                  {stop.type}
                </strong>
                <div style={{ marginTop: '4px' }}>{stop.label}</div>
                {stop.duration_hours > 0 && (
                  <div style={{ color: '#5B6066', marginTop: '2px' }}>
                    Duration: {formatDuration(stop.duration_hours)}
                  </div>
                )}
                {stop.start && (
                  <div style={{ color: '#5B6066', marginTop: '2px', fontSize: '11px' }}>
                    {new Date(stop.start).toLocaleString()}
                  </div>
                )}
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}
