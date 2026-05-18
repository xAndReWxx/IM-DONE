/* ============================================================
 * PhysioAI Pro V2 — useAutonomousGaze (exported as useEyeFocus)
 * ============================================================
 * Drives saccadic eye movement with no mouse/pointer tracking.
 *
 * Behaviour:
 *   • Quick "saccade" jumps to a random target in [-1, 1]
 *   • Pauses at the target for 0.8–2.5 seconds (biological dwell time)
 *   • Applies subtle micro-tremor while paused (realistic fixation jitter)
 *   • Exported as `useEyeFocus` for backward compatibility
 * ============================================================ */

import { useEffect, useRef, useState } from "react";

type Pos = { x: number; y: number };

function rand(min: number, max: number): number {
  return min + Math.random() * (max - min);
}

/** Generate a random gaze target within the visible disk (not the corners). */
function randomTarget(): Pos {
  // Pick within a circle of radius 0.85 so the pupil never clips the iris rim.
  const angle = rand(0, Math.PI * 2);
  const dist = rand(0.1, 0.85);
  return {
    x: Math.cos(angle) * dist,
    y: Math.sin(angle) * dist,
  };
}

export function useEyeFocus(): Pos {
  const [pos, setPos] = useState<Pos>({ x: 0, y: 0 });

  // Internal saccade state kept in refs so we don't re-render on each tick.
  const targetRef = useRef<Pos>({ x: 0, y: 0 });
  const currentRef = useRef<Pos>({ x: 0, y: 0 });
  const dwellUntilRef = useRef<number>(0);      // performance.now() when dwell ends
  const saccadingRef = useRef<boolean>(false);   // true during the fast jump phase
  const rafRef = useRef<number>(0);

  useEffect(() => {
    // Seed with a random first target.
    targetRef.current = randomTarget();
    dwellUntilRef.current = performance.now() + rand(800, 2500);

    const tick = (now: number) => {
      const cur = currentRef.current;
      const tgt = targetRef.current;

      if (saccadingRef.current) {
        // Fast saccade: lerp at ~60% per frame (arrives in ~3-4 frames at 60fps).
        const nx = cur.x + (tgt.x - cur.x) * 0.6;
        const ny = cur.y + (tgt.y - cur.y) * 0.6;
        const distLeft = Math.hypot(tgt.x - nx, tgt.y - ny);

        currentRef.current = { x: nx, y: ny };

        if (distLeft < 0.015) {
          // Arrived — snap and start dwelling.
          currentRef.current = { ...tgt };
          saccadingRef.current = false;
          dwellUntilRef.current = now + rand(800, 2500);
        }
      } else {
        // Dwell phase: add micro-tremor (small high-frequency oscillation).
        const tremorAmp = 0.008;
        const tremorX = (Math.sin(now * 0.047) + Math.sin(now * 0.083)) * tremorAmp;
        const tremorY = (Math.cos(now * 0.059) + Math.cos(now * 0.031)) * tremorAmp;

        currentRef.current = {
          x: tgt.x + tremorX,
          y: tgt.y + tremorY,
        };

        if (now >= dwellUntilRef.current) {
          // Dwell over — pick next target and begin saccade.
          targetRef.current = randomTarget();
          saccadingRef.current = true;
        }
      }

      setPos({ ...currentRef.current });
      rafRef.current = requestAnimationFrame(tick);
    };

    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
  }, []);

  return pos;
}
