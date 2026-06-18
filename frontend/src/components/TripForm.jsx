import { useState } from 'react';

export default function TripForm({ onSubmit, loading, error }) {
  const [currentCity,    setCurrentCity]    = useState('');
  const [currentState,   setCurrentState]   = useState('');
  const [pickupCity,     setPickupCity]     = useState('');
  const [pickupState,    setPickupState]    = useState('');
  const [dropoffCity,    setDropoffCity]    = useState('');
  const [dropoffState,   setDropoffState]   = useState('');
  const [cycleUsed,      setCycleUsed]      = useState(0);
  const [gettingLoc,     setGettingLoc]     = useState(false);
  const [locActive,      setLocActive]      = useState(false);
  const [useYm,          setUseYm]          = useState(true);
  const [usePc,          setUsePc]          = useState(false);

  const fmt = (city, state) => state ? `${city}, ${state}` : city;

  const handleSubmit = (e) => {
    e.preventDefault();
    onSubmit({
      current_location:  fmt(currentCity, currentState),
      pickup_location:   fmt(pickupCity, pickupState),
      dropoff_location:  fmt(dropoffCity, dropoffState),
      current_cycle_used: parseFloat(cycleUsed),
      use_ym: useYm,
      use_pc: usePc,
    });
  };

  const handleGetLocation = () => {
    if (!navigator.geolocation) { alert('Geolocation not supported'); return; }
    setGettingLoc(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setCurrentCity(`${pos.coords.latitude.toFixed(5)},${pos.coords.longitude.toFixed(5)}`);
        setCurrentState('');
        setLocActive(true);
        setGettingLoc(false);
      },
      () => { alert('Unable to get location — check browser permissions.'); setGettingLoc(false); },
      { timeout: 10000, maximumAge: 60000 }
    );
  };

  return (
    <div className="form-card">
      <div className="form-card-header">
        <h2>Trip Details</h2>
      </div>

      <form onSubmit={handleSubmit} className="form-card-body">

        {/* Current location */}
        <div className="field-group">
          <div className="loc-label-row">
            <span className="field-label">Current Location</span>
            <button type="button" className="use-loc-btn" onClick={handleGetLocation} disabled={gettingLoc}>
              {gettingLoc ? 'Getting…' : '📍 Use My Location'}
            </button>
          </div>
          <div className="field-row">
            <input type="text" value={currentCity}
              onChange={(e) => { setCurrentCity(e.target.value); setLocActive(false); }}
              placeholder="City or lat,lng" required />
            <input type="text" value={currentState}
              onChange={(e) => setCurrentState(e.target.value)}
              placeholder="State" disabled={locActive} />
          </div>
        </div>

        {/* Pickup */}
        <div className="field-group">
          <span className="field-label">Pickup Location</span>
          <div className="field-row">
            <input type="text" value={pickupCity}
              onChange={(e) => setPickupCity(e.target.value)}
              placeholder="City" required />
            <input type="text" value={pickupState}
              onChange={(e) => setPickupState(e.target.value)}
              placeholder="State" />
          </div>
        </div>

        {/* Dropoff */}
        <div className="field-group">
          <span className="field-label">Dropoff Location</span>
          <div className="field-row">
            <input type="text" value={dropoffCity}
              onChange={(e) => setDropoffCity(e.target.value)}
              placeholder="City" required />
            <input type="text" value={dropoffState}
              onChange={(e) => setDropoffState(e.target.value)}
              placeholder="State" />
          </div>
        </div>

        {/* Cycle used */}
        <div className="field-group">
          <span className="field-label">8-Day Cycle Used (Hours)</span>
          <input type="number" step="0.5" min="0" max="70"
            value={cycleUsed}
            onChange={(e) => setCycleUsed(e.target.value)}
            required />
        </div>

        {/* Options */}
        <div className="options-box">
          <label className="check-label">
            <input type="checkbox" checked={useYm} onChange={(e) => setUseYm(e.target.checked)} />
            Log 15-min Yard Moves (YM) at pickup/dropoff
          </label>
          <label className="check-label">
            <input type="checkbox" checked={usePc} onChange={(e) => setUsePc(e.target.checked)} />
            Include 30-min Personal Conveyance (PC) at end
          </label>
        </div>

        {error && <div className="error-banner">{error}</div>}

        <button type="submit" className="primary" disabled={loading}>
          {loading ? 'Planning route…' : 'Plan Trip →'}
        </button>
      </form>
    </div>
  );
}
