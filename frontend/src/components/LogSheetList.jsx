import LogSheet from './LogSheet';

export default function LogSheetList({ logs }) {
  if (!logs || logs.length === 0) return null;

  return (
    <div>
      <div className="logs-header no-print">
        <h2>{logs.length} Daily Log{logs.length !== 1 ? 's' : ''}</h2>
        <button className="print-btn" onClick={() => window.print()}>
          🖨 Print Logs
        </button>
      </div>
      {logs.map((log, i) => (
        <LogSheet key={i} log={log} />
      ))}
    </div>
  );
}
