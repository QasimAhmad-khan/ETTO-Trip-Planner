const STATUS_COLORS = { OFF: '#9AA0A6', SB: '#3D4F7C', D: '#2F7D5B', ON: '#B07A2E' };
const STATUS_LABELS = { OFF: 'Off Duty', SB: 'Sleeper Berth', D: 'Driving', ON: 'On Duty ND' };
const ROW_KEYS = ['OFF', 'SB', 'D', 'ON'];

// Layout — matches original proportions
const LW  = 130;   // label column
const GW  = 864;   // grid (36px/hr × 24)
const TW  = 60;    // totals column
const SW  = LW + GW + TW + 8;

const HH  = 52;    // header height
const RH  = 36;    // row height
const GH  = RH * 4;
const RMH = 100;   // remarks strip — tall enough for 60° angled labels
const SH  = HH + GH + RMH + 8;

const PH  = GW / 24;
const PM  = GW / 1440;

const gx  = m   => LW + m * PM;
const gy  = key => HH + ROW_KEYS.indexOf(key) * RH + RH / 2;
const hLbl = h  => h === 0 || h === 24 ? 'M' : h === 12 ? 'N' : String(h > 12 ? h - 12 : h);

export default function LogSheet({ log }) {
  if (!log) return null;
  const { date, total_miles, totals, segments } = log;

  // Stepped status path
  let pathD = '';
  if (segments?.length > 0) {
    pathD = `M ${gx(segments[0].start_min).toFixed(1)} ${gy(segments[0].status).toFixed(1)}`;
    for (let i = 0; i < segments.length; i++) {
      const s  = segments[i];
      const x0 = gx(s.start_min), x1 = gx(s.end_min), y = gy(s.status);
      if (i > 0 && segments[i - 1].status !== s.status)
        pathD += ` L ${x0.toFixed(1)} ${y.toFixed(1)}`;
      pathD += ` L ${x1.toFixed(1)} ${y.toFixed(1)}`;
    }
  }

  // Deduplicated remark items
  const remarkItems = [];
  segments?.forEach((seg, i) => {
    if (seg.remark && (i === 0 || seg.remark !== segments[i - 1].remark)) {
      remarkItems.push({ x: gx(seg.start_min), remark: seg.remark });
    }
  });

  const totalHrs = Object.values(totals).reduce((a, b) => a + b, 0);

  // Colours
  const BORDER = '#8A8680';
  const MAJOR  = '#AAAAAA';
  const MINOR  = '#D0CCC4';
  const TICK   = '#E6E2DA';
  const INK    = '#1A1C1E';
  const SEC    = '#5B6066';
  const HDR    = '#EDE9E0';
  const ROW_A  = '#FFFFFF';
  const ROW_B  = '#F5F3EF';

  return (
    <div className="log-card print-page">
      <svg
        viewBox={`0 0 ${SW} ${SH}`}
        width="100%"
        style={{ display: 'block', minWidth: 700 }}
        aria-label={`Driver's Daily Log — ${date}`}
      >
        {/* Background */}
        <rect x="0" y="0" width={SW} height={SH} fill={ROW_A} />

        {/* ── Header ──────────────────────────────────────────────── */}
        <rect x="0" y="0" width={SW} height={HH} fill={HDR} />
        <line x1="0" y1={HH} x2={SW} y2={HH} stroke={BORDER} strokeWidth="1.5" />

        <text x="8"   y="18" fontSize="9"  fill={SEC} fontFamily="Hanken Grotesk, sans-serif" fontWeight="600" letterSpacing="0.5">DATE</text>
        <text x="8"   y="38" fontSize="15" fill={INK} fontWeight="700" fontFamily="Hanken Grotesk, sans-serif">{date}</text>

        <text x={LW + 8} y="18" fontSize="9"  fill={SEC} fontFamily="Hanken Grotesk, sans-serif" fontWeight="600" letterSpacing="0.5">TOTAL MILES</text>
        <text x={LW + 8} y="38" fontSize="14" fill={INK} fontWeight="600" fontFamily="JetBrains Mono, monospace">{total_miles ?? 0}</text>

        <text x={LW + 130} y="18" fontSize="9"  fill={SEC} fontFamily="Hanken Grotesk, sans-serif" fontWeight="600" letterSpacing="0.5">CARRIER</text>
        <text x={LW + 130} y="38" fontSize="12" fill={INK} fontFamily="Hanken Grotesk, sans-serif">ETTO Logistics</text>

        <text x={LW + GW - 80} y="18" fontSize="9"  fill={SEC} fontFamily="Hanken Grotesk, sans-serif" fontWeight="600" letterSpacing="0.5">CYCLE</text>
        <text x={LW + GW - 80} y="38" fontSize="11" fill={SEC} fontFamily="Hanken Grotesk, sans-serif">70-hr / 8-day</text>

        <text x={LW + GW + 8} y="18" fontSize="9" fill={SEC} fontFamily="Hanken Grotesk, sans-serif" fontWeight="600" letterSpacing="0.5">HRS</text>

        {/* Top hour labels */}
        {Array.from({ length: 25 }, (_, h) => (
          <text key={`ht${h}`}
            x={LW + h * PH} y={HH - 5}
            fontSize="9.5" textAnchor="middle" fill={SEC}
            fontFamily="JetBrains Mono, monospace">
            {hLbl(h)}
          </text>
        ))}

        {/* ── Vertical grid lines ──────────────────────────────────── */}
        {[0, 6, 12, 18, 24].map(h => (
          <line key={`maj${h}`}
            x1={LW + h * PH} y1={HH}
            x2={LW + h * PH} y2={HH + GH}
            stroke={MAJOR} strokeWidth="1" />
        ))}
        {Array.from({ length: 25 }, (_, h) => h % 6 !== 0 && (
          <line key={`min${h}`}
            x1={LW + h * PH} y1={HH}
            x2={LW + h * PH} y2={HH + GH}
            stroke={MINOR} strokeWidth="0.75" />
        ))}
        {Array.from({ length: 24 }, (_, h) =>
          [1, 2, 3].map(q => (
            <line key={`t${h}_${q}`}
              x1={LW + (h + q / 4) * PH} y1={HH}
              x2={LW + (h + q / 4) * PH} y2={HH + GH}
              stroke={TICK} strokeWidth="0.5"
              strokeDasharray="2,3" />
          ))
        )}

        {/* ── Row bands ────────────────────────────────────────────── */}
        {ROW_KEYS.map((key, ri) => {
          const ry = HH + ri * RH;
          const bg = ri % 2 === 0 ? ROW_A : ROW_B;
          return (
            <g key={key}>
              <rect x={LW} y={ry} width={GW} height={RH} fill={bg} />
              <rect x={5}  y={ry} width={LW - 5} height={RH} fill={bg} />
              {/* Status colour bar */}
              <rect x="0" y={ry} width="4" height={RH} fill={STATUS_COLORS[key]} />
              {/* Label */}
              <text x={LW - 6} y={ry + RH / 2 + 4}
                fontSize="11" textAnchor="end" fill={INK}
                fontFamily="Hanken Grotesk, sans-serif">
                {STATUS_LABELS[key]}
              </text>
              {/* Horizontal rule */}
              <line x1="0" y1={ry + RH} x2={LW + GW + TW + 8} y2={ry + RH}
                stroke={BORDER} strokeWidth={ri === 3 ? 1.25 : 0.6} />
              {/* Row total */}
              <text x={LW + GW + TW / 2 + 4} y={ry + RH / 2 + 5}
                fontSize="13" textAnchor="middle"
                fill={totals[key] > 0 ? INK : '#CCCCCC'}
                fontWeight={totals[key] > 0 ? '600' : '400'}
                fontFamily="JetBrains Mono, monospace">
                {(totals[key] ?? 0).toFixed(1)}
              </text>
            </g>
          );
        })}

        {/* Active-status subtle fill per segment */}
        {segments?.map((seg, i) => {
          const x0 = gx(seg.start_min);
          const x1 = gx(seg.end_min);
          const ry = HH + ROW_KEYS.indexOf(seg.status) * RH;
          if (x1 - x0 < 1) return null;
          return (
            <rect key={`f${i}`}
              x={x0} y={ry} width={x1 - x0} height={RH}
              fill={STATUS_COLORS[seg.status]} opacity="0.10" />
          );
        })}

        {/* Grid outer border */}
        <rect x={LW} y={HH} width={GW} height={GH}
          fill="none" stroke={BORDER} strokeWidth="1.5" />

        {/* Totals column divider */}
        <line x1={LW + GW} y1={HH} x2={LW + GW} y2={HH + GH}
          stroke={BORDER} strokeWidth="1" />

        {/* ── Status line ─────────────────────────────────────────── */}
        {pathD && (
          <path d={pathD} fill="none"
            stroke="#1F4E66"
            strokeWidth="2.5"
            strokeLinejoin="miter"
            strokeLinecap="square" />
        )}

        {/* ── Remarks strip ────────────────────────────────────────── */}
        <line x1={LW} y1={HH + GH}
          x2={LW + GW} y2={HH + GH}
          stroke={BORDER} strokeWidth="1" />

        <text x="8" y={HH + GH + 16}
          fontSize="9" fill={SEC}
          fontFamily="Hanken Grotesk, sans-serif" fontWeight="600" letterSpacing="0.5">
          REMARKS
        </text>

        {/* Remarks: 60° angled labels — never overlap regardless of proximity */}
        {remarkItems.map(({ x, remark }, i) => {
          const pivotY = HH + GH + 6;
          const label  = remark.length > 22 ? remark.slice(0, 20) + '…' : remark;
          return (
            <g key={i}>
              <line x1={x} y1={HH + GH} x2={x} y2={pivotY}
                stroke={SEC} strokeWidth="0.75" />
              <text
                x={x + 2} y={pivotY + 1}
                fontSize="9" fill={SEC}
                fontFamily="Hanken Grotesk, sans-serif"
                transform={`rotate(60, ${x + 2}, ${pivotY + 1})`}
              >
                {label}
              </text>
            </g>
          );
        })}

        {/* ── Total sum (bottom-right) ──────────────────────────────── */}
        <line x1={LW + GW} y1={HH + GH}
          x2={LW + GW} y2={HH + GH + 30}
          stroke={BORDER} strokeWidth="0.75" />
        <text x={LW + GW + TW / 2 + 4} y={HH + GH + 18}
          fontSize="12" textAnchor="middle" fill={INK} fontWeight="700"
          fontFamily="JetBrains Mono, monospace">
          {totalHrs.toFixed(1)}
        </text>
        <text x={LW + GW + TW / 2 + 4} y={HH + GH + 30}
          fontSize="8.5" textAnchor="middle" fill={SEC}
          fontFamily="Hanken Grotesk, sans-serif">
          of 24
        </text>
      </svg>
    </div>
  );
}
