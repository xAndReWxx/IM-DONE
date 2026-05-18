/* ============================================================
 * PhysioAI Pro V2 — RoboticEye
 * ============================================================
 * A single SVG eye. Rendered twice (left + right) by LandingScreen.
 *
 * Props:
 *   side    — "left" | "right" — controls the status label text
 *             and a slight blink-animation offset between the two eyes.
 *   gazeX   — gaze x position in [-1, 1] (from parent)
 *   gazeY   — gaze y position in [-1, 1] (from parent)
 *
 * The component no longer calls useEyeFocus internally — the
 * parent provides gaze values, which lets the right eye lag
 * 200 ms behind the left to simulate independent ocular motion.
 * ============================================================ */

import "./RoboticEye.css";

type Props = {
  side: "left" | "right";
  gazeX: number;
  gazeY: number;
};

export function RoboticEye({ side, gazeX, gazeY }: Props) {
  // Max pupil travel from the iris center, in SVG units.
  const MAX_TRAVEL = 28;

  // Clamp the gaze to a circular range so the pupil moves in a disk.
  const distance = Math.min(1, Math.hypot(gazeX, gazeY));
  const angle = Math.atan2(gazeY, gazeX);
  const pupilTX = Math.cos(angle) * distance * MAX_TRAVEL;
  const pupilTY = Math.sin(angle) * distance * MAX_TRAVEL;

  // Generate evenly-spaced tick marks around the rim.
  const tickCount = 48;
  const ticks = Array.from({ length: tickCount }, (_, i) => {
    const a = (i / tickCount) * Math.PI * 2;
    const isMajor = i % 6 === 0;
    const r1 = 168;
    const r2 = r1 - (isMajor ? 14 : 8);
    return {
      x1: 200 + Math.cos(a) * r1,
      y1: 200 + Math.sin(a) * r1,
      x2: 200 + Math.cos(a) * r2,
      y2: 200 + Math.sin(a) * r2,
      isMajor,
    };
  });

  const sensorLabel = side === "left" ? "SENSOR-L" : "SENSOR-R";
  const modifierClass = side === "left" ? "eye--left" : "eye--right";

  return (
    <div
      className={`eye ${modifierClass}`}
      role="img"
      aria-label={`PhysioAI ${side} eye watching`}
    >
      <div className="eye__blink">
        <svg viewBox="0 0 400 400" className="eye__svg">
          {/* ── Outer ring (instrument bezel) ── */}
          <circle cx="200" cy="200" r="180" className="eye__bezel-outer" />
          <circle cx="200" cy="200" r="172" className="eye__bezel-mid" />

          {/* ── Tick marks (rotating slowly) ── */}
          <g className="eye__ticks">
            {ticks.map((t, i) => (
              <line
                key={i}
                x1={t.x1} y1={t.y1} x2={t.x2} y2={t.y2}
                className={t.isMajor ? "eye__tick eye__tick--major" : "eye__tick"}
              />
            ))}
          </g>

          {/* ── Eye socket ── */}
          <circle cx="200" cy="200" r="148" className="eye__sclera" />
          <circle cx="200" cy="200" r="148" className="eye__sclera-stroke" />

          {/* ── Iris + pupil group (translated by gaze props) ── */}
          <g
            style={{
              transform: `translate(${pupilTX}px, ${pupilTY}px)`,
              transition: "transform 55ms linear",
            }}
          >
            {/* Iris outer ring */}
            <circle cx="200" cy="200" r="78" className="eye__iris" />
            <circle cx="200" cy="200" r="78" className="eye__iris-stroke" />
            {/* Aperture-style segments */}
            <g className="eye__aperture">
              {[0, 60, 120, 180, 240, 300].map((deg) => (
                <line
                  key={deg}
                  x1="200" y1="200"
                  x2={200 + Math.cos((deg * Math.PI) / 180) * 78}
                  y2={200 + Math.sin((deg * Math.PI) / 180) * 78}
                />
              ))}
            </g>
            {/* Pupil */}
            <circle cx="200" cy="200" r="36" className="eye__pupil" />
            {/* Specular highlight */}
            <circle cx="184" cy="184" r="9" className="eye__highlight" />
            <circle cx="218" cy="208" r="3" className="eye__highlight eye__highlight--small" />
          </g>

          {/* ── Status text around the rim (instrument labels) ── */}
          <text x="200" y="48"  className="eye__label" textAnchor="middle">{sensorLabel}</text>
          <text x="200" y="362" className="eye__label" textAnchor="middle">PHYSIOAI · V2</text>
          <text x="32"  y="204" className="eye__label" textAnchor="start">READY</text>
          <text x="368" y="204" className="eye__label" textAnchor="end">ONLINE</text>
        </svg>
      </div>

      {/* Subtle scanning beam */}
      <div className="eye__scan" aria-hidden />
    </div>
  );
}
