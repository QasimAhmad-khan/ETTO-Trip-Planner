export default function TripSummary({ summary }) {
  if (!summary) return null;

  const arrival = new Date(summary.arrival_time);
  const arrivalStr = isNaN(arrival) ? '—' : arrival.toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  });

  const stats = [
    { label: 'Total Distance',  value: `${summary.total_distance_mi} mi` },
    { label: 'Drive Time',      value: `${summary.total_drive_hours} hrs` },
    { label: 'On-Duty Time',    value: `${summary.total_on_duty_hours} hrs` },
    { label: 'Elapsed Time',    value: `${summary.total_elapsed_hours} hrs` },
    { label: 'Est. Arrival',    value: arrivalStr, wide: true },
    { label: 'Log Sheets',      value: `${summary.log_sheets} day${summary.log_sheets !== 1 ? 's' : ''}` },
  ];

  return (
    <div className="summary-card">
      <div className="summary-card-header">Trip Summary</div>

      {summary.restart_required && (
        <div className="restart-banner">
          ⚠ Cycle exhausted — 34-hr restart inserted before or during trip.
        </div>
      )}

      <div className="stat-grid">
        {stats.map(({ label, value, wide }) => (
          <div className="stat-tile" key={label}>
            <div className="stat-label">{label}</div>
            <div className={`stat-value${wide ? ' wide' : ''}`}>{value}</div>
          </div>
        ))}
      </div>

      {summary.rounding && (
        <div className="summary-note">{summary.rounding}</div>
      )}
    </div>
  );
}
