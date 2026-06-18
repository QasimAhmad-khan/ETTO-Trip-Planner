import { useState, useEffect } from 'react'
import TripForm from './components/TripForm'
import TripSummary from './components/TripSummary'
import RouteMap from './components/RouteMap'
import LogSheetList from './components/LogSheetList'
import { planTrip } from './lib/api'

function App() {
  const [data, setData]               = useState(null);
  const [loading, setLoading]         = useState(false);
  const [error, setError]             = useState(null);
  const [initialLoading, setInitial]  = useState(true);

  useEffect(() => {
    const t = setTimeout(() => setInitial(false), 1200);
    return () => clearTimeout(t);
  }, []);

  if (initialLoading) {
    return (
      <div style={{ display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', height:'100vh', background:'var(--color-paper)' }}>
        <div style={{ display:'flex', alignItems:'center', gap:'0.75rem', marginBottom:'2rem' }}>
          <div style={{ width:42, height:42, background:'var(--color-primary)', borderRadius:8, display:'flex', alignItems:'center', justifyContent:'center', color:'#fff', fontWeight:700, fontSize:22 }}>E</div>
          <div>
            <div style={{ fontSize:'var(--text-lg)', fontWeight:700, color:'var(--color-primary)' }}>ETTO Trip Planner</div>
            <div style={{ fontSize:'var(--text-xs)', color:'var(--color-secondary)' }}>HOS-Compliant Route &amp; Logbook Generator</div>
          </div>
        </div>
        <div style={{ width:36, height:36, border:'3px solid var(--color-hairline)', borderTop:'3px solid var(--color-primary)', borderRadius:'50%', animation:'spin 0.9s linear infinite' }} />
        <style>{`@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}`}</style>
      </div>
    );
  }

  const handlePlanTrip = async (payload) => {
    setLoading(true);
    setError(null);
    try {
      const result = await planTrip(payload);
      setData(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      {/* ── Header ─────────────────────────────────────────────────── */}
      <header className="app-header no-print">
        <div className="app-logo-mark">E</div>
        <div>
          <div className="app-logo-name">ETTO Trip Planner</div>
          <div className="app-logo-sub">FMCSA HOS-Compliant Route &amp; ELD Logbook Generator · 70 hr / 8-day Cycle</div>
        </div>
      </header>

      <div className="layout-grid">
        {/* ── Left sidebar ─────────────────────────────────────────── */}
        <div className="sidebar no-print">
          <TripForm onSubmit={handlePlanTrip} loading={loading} error={error} />

          {data?.summary?.warnings?.length > 0 && (
            <div className="warning-banner" style={{ marginTop:'1rem' }}>
              <strong>Routing Warning</strong>
              <ul style={{ margin:'0.4rem 0 0 1.25rem' }}>
                {data.summary.warnings.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            </div>
          )}

          <TripSummary summary={data?.summary} />
        </div>

        {/* ── Right content ────────────────────────────────────────── */}
        <div>
          {data && data.route ? (
            <>
              <div className="no-print">
                <p className="section-label">Route Map</p>
                <RouteMap route={data.route} stops={data.stops} />
              </div>

              <p className="section-label no-print">Driver's Daily Logs</p>
              <LogSheetList logs={data.logs} />
            </>
          ) : (
            !loading && (
              <div style={{ display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center', minHeight:320, color:'var(--color-secondary)', textAlign:'center', gap:'0.75rem' }}>
                <svg width="56" height="56" viewBox="0 0 56 56" fill="none" style={{ opacity:0.3 }}>
                  <rect x="4" y="4" width="48" height="48" rx="8" stroke="currentColor" strokeWidth="2" fill="none"/>
                  <line x1="14" y1="20" x2="42" y2="20" stroke="currentColor" strokeWidth="2"/>
                  <line x1="14" y1="28" x2="42" y2="28" stroke="currentColor" strokeWidth="2"/>
                  <line x1="14" y1="36" x2="30" y2="36" stroke="currentColor" strokeWidth="2"/>
                </svg>
                <div style={{ fontWeight:600, fontSize:'var(--text-md)', color:'var(--color-ink)' }}>Enter trip details to get started</div>
                <div style={{ fontSize:'var(--text-xs)', maxWidth:280 }}>Fill in origin, pickup, and dropoff locations on the left to generate your HOS-compliant route and ELD log sheets.</div>
              </div>
            )
          )}

          {loading && (
            <div style={{ display:'flex', alignItems:'center', justifyContent:'center', minHeight:320, gap:'1rem', color:'var(--color-secondary)' }}>
              <div style={{ width:28, height:28, border:'3px solid var(--color-hairline)', borderTop:'3px solid var(--color-primary)', borderRadius:'50%', animation:'spin 0.9s linear infinite' }} />
              <span style={{ fontSize:'var(--text-sm)' }}>Calculating route and HOS schedule…</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default App
