/* ============================================================
 * PhysioAI Pro V2 — PostureGauge
 * ============================================================
 * Half-circle SVG dial that displays the live posture score
 * (0-100). Built to feel like an analog gauge on a control
 * panel — tick marks + a needle that eases toward new values.
 *
 * COLOR LOGIC
 *   < 60  → red signal     (significant issues)
 *   60-79 → amber signal   (warning)
 *   ≥ 80  → calm green     (good posture)
 *
 * The needle is hard-clamped to [0, 100] and smoothly animated
 * with a CSS transition.
 * ============================================================ */

import "./PostureGauge.css";

type Props = {
  score: number | null;        // 0..100 or null when no detection
  label?: string;
};

export function PostureGauge({ score, label = "POSTURE" }: Props) {
  // Map score (0..100) to angle (-90deg .. +90deg) — left to right
  const value = score == null ? 0 : Math.max(0, Math.min(100, score));
  const angle = -90 + (value / 100) * 180;

  // Pick a signal color based on score band
  const band =
    score == null ? "off"
      : score < 60 ? "bad"
      : score < 80 ? "warn"
      : "good";

  // Generate tick marks every 10 units
  const ticks = Array.from({ length: 11 }, (_, i) => {
    const t = (i / 10) * 180 - 90;
    const isMajor = i % 5 === 0;
    const len = isMajor ? 10 : 6;
    const r1 = 86;
    const r2 = r1 - len;
    const rad = (t * Math.PI) / 180;
    return {
      x1: 100 + Math.cos(rad) * r1,
      y1: 100 + Math.sin(rad) * r1,
      x2: 100 + Math.cos(rad) * r2,
      y2: 100 + Math.sin(rad) * r2,
      isMajor,
    };
  });

  return (
    <div className={`gauge gauge--${band}`}>
      <svg viewBox="0 0 200 120" className="gauge__svg">
        {/* Arc backdrop */}
        <path
          d="M 14 100 A 86 86 0 0 1 186 100"
          className="gauge__arc"
        />
        {/* Filled arc up to current value */}
        <path
          d={describeFillArc(value)}
          className="gauge__arc-fill"
        />
        {/* Ticks */}
        {ticks.map((t, i) => (
          <line
            key={i}
            x1={t.x1} y1={t.y1} x2={t.x2} y2={t.y2}
            className={t.isMajor ? "gauge__tick gauge__tick--major" : "gauge__tick"}
          />
        ))}
        {/* Center pivot */}
        <circle cx="100" cy="100" r="4" className="gauge__pivot" />
        {/* Needle */}
        <g style={{ transformOrigin: "100px 100px", transform: `rotate(${angle}deg)`, transition: "transform 350ms cubic-bezier(.4,0,.2,1)" }}>
          <line x1="100" y1="100" x2="100" y2="22" className="gauge__needle" />
        </g>
      </svg>

      <div className="gauge__readout">
        <div className="gauge__value mono">
          {score == null ? "—" : Math.round(value)}
        </div>
        <div className="label gauge__label">{label}</div>
      </div>
    </div>
  );
}

/** Build SVG path for the filled portion of the gauge arc. */
function describeFillArc(value: number): string {
  const t = (value / 100) * 180 - 90;
  const rad = (t * Math.PI) / 180;
  const x = 100 + Math.cos(rad) * 86;
  const y = 100 + Math.sin(rad) * 86;
  const large = value > 50 ? 1 : 0;
  return `M 14 100 A 86 86 0 0 ${large} ${x.toFixed(2)} ${y.toFixed(2)}`;
}
