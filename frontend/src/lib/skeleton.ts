/* ============================================================
 * PhysioAI Pro V2 — Skeleton Rendering
 * ============================================================
 * Pure rendering function that takes a list of MediaPipe
 * landmarks and draws a skeleton overlay onto a canvas. Kept
 * separate from the React component so it's easy to unit-test
 * and swap out (e.g. for SVG-based rendering later).
 *
 * COORDINATE SPACE
 *   MediaPipe gives normalized [0..1] coords. We map them into
 *   the canvas with a small inner padding so the skeleton never
 *   touches the panel edges.
 *
 * MIRRORING
 *   The phone's selfie camera is naturally mirrored. We pass
 *   `mirror: true` to match the video preview so left/right
 *   visually correspond to the user's body.
 * ============================================================ */

import type { Landmark } from "./websocket-types";

/**
 * MediaPipe Pose connections (33 landmarks).
 * Each [a, b] pair is one bone segment to stroke.
 */
export const POSE_CONNECTIONS: ReadonlyArray<[number, number]> = [
  // Face
  [0, 1], [1, 2], [2, 3], [3, 7],
  [0, 4], [4, 5], [5, 6], [6, 8],
  [9, 10],
  // Torso
  [11, 12], [11, 23], [12, 24], [23, 24],
  // Left arm
  [11, 13], [13, 15], [15, 17], [15, 19], [15, 21], [17, 19],
  // Right arm
  [12, 14], [14, 16], [16, 18], [16, 20], [16, 22], [18, 20],
  // Left leg
  [23, 25], [25, 27], [27, 29], [29, 31], [27, 31],
  // Right leg
  [24, 26], [26, 28], [28, 30], [30, 32], [28, 32],
];

export type SkeletonStyle = {
  mirror?: boolean;
  lineColor?: string;
  jointColor?: string;
  lineWidth?: number;
  jointRadius?: number;
  minVisibility?: number;
};

/**
 * Render a skeleton from MediaPipe landmarks onto a 2D canvas.
 * Assumes `ctx`'s transform has been set up for the canvas's
 * logical (CSS pixel) size, not its devicePixelRatio buffer.
 */
export function drawSkeleton(
  ctx: CanvasRenderingContext2D,
  landmarks: Landmark[],
  width: number,
  height: number,
  style: SkeletonStyle = {},
) {
  const {
    mirror = true,
    lineColor = "rgba(244,241,234,0.75)",
    jointColor = "#f4f1ea",
    lineWidth = 1.5,
    jointRadius = 3,
    minVisibility = 0.5,
  } = style;

  // No arbitrary inner padding. The skeleton MUST align 1:1 with the video source.
  const mapPt = (lm: Landmark) => ({
    x: mirror ? width - (lm.x * width) : lm.x * width,
    y: lm.y * height,
    visible: lm.visibility >= minVisibility,
  });

  // ── Strokes (bones) ──
  ctx.lineWidth = lineWidth;
  ctx.strokeStyle = lineColor;
  ctx.lineCap = "round";
  ctx.beginPath();
  for (const [a, b] of POSE_CONNECTIONS) {
    const p1 = mapPt(landmarks[a]);
    const p2 = mapPt(landmarks[b]);
    if (!p1.visible || !p2.visible) continue;
    ctx.moveTo(p1.x, p1.y);
    ctx.lineTo(p2.x, p2.y);
  }
  ctx.stroke();

  // ── Joints ──
  ctx.fillStyle = jointColor;
  for (const lm of landmarks) {
    const p = mapPt(lm);
    if (!p.visible) continue;
    ctx.beginPath();
    ctx.arc(p.x, p.y, jointRadius, 0, Math.PI * 2);
    ctx.fill();
  }
}
