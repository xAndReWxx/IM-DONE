/* ============================================================
 * PhysioAI Pro V2 — CameraOverlay
 * ============================================================
 * Stacks a <video> (the camera preview) and a <canvas> (the
 * skeleton overlay). The canvas is sized to match the video's
 * displayed dimensions and uses devicePixelRatio scaling so
 * lines stay sharp on Retina / high-DPI screens.
 *
 * The video is mirrored (transform: scaleX(-1)) so the selfie
 * camera feels natural; the skeleton renderer also receives
 * `mirror: true` so the two stay in sync visually.
 *
 * COMPONENT IS HEADLESS-VISUAL
 *   It doesn't own the camera stream or the WS; it only:
 *     • Forwards a videoRef so the parent can call play()/stop()
 *     • Draws whatever `landmarks` prop it receives each render
 * ============================================================ */

import { forwardRef, useEffect, useRef } from "react";
import type { Landmark } from "@/lib/websocket-types";
import { drawSkeleton } from "@/lib/skeleton";
import "./CameraOverlay.css";

type Props = {
  /** Landmarks from the WS; null when no person detected yet */
  landmarks: Landmark[] | null;
  /** Show the "stand in frame" hint */
  showHint?: boolean;
};

export const CameraOverlay = forwardRef<HTMLVideoElement, Props>(
  function CameraOverlay({ landmarks, showHint }, videoRef) {
    const canvasRef = useRef<HTMLCanvasElement | null>(null);
    const wrapRef = useRef<HTMLDivElement | null>(null);

    // Resize the canvas backing store whenever the wrapper resizes.
    useEffect(() => {
      const canvas = canvasRef.current;
      const wrap = wrapRef.current;
      if (!canvas || !wrap) return;

      const resize = () => {
        const dpr = Math.min(2, window.devicePixelRatio || 1);
        const r = wrap.getBoundingClientRect();
        canvas.width = Math.floor(r.width * dpr);
        canvas.height = Math.floor(r.height * dpr);
        canvas.style.width = `${r.width}px`;
        canvas.style.height = `${r.height}px`;
        const ctx = canvas.getContext("2d");
        ctx?.setTransform(dpr, 0, 0, dpr, 0, 0);
      };

      resize();
      const ro = new ResizeObserver(resize);
      ro.observe(wrap);
      return () => ro.disconnect();
    }, []);

    // Redraw skeleton whenever new landmarks arrive.
    useEffect(() => {
      const canvas = canvasRef.current;
      const wrap = wrapRef.current;
      if (!canvas || !wrap) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      const r = wrap.getBoundingClientRect();
      ctx.clearRect(0, 0, r.width, r.height);
      if (landmarks && landmarks.length === 33) {
        drawSkeleton(ctx, landmarks, r.width, r.height, { mirror: true });
      }
    }, [landmarks]);

    return (
      <div className="camera" ref={wrapRef}>
        {/* Hairline frame */}
        <div className="camera__bracket camera__bracket--tl" aria-hidden />
        <div className="camera__bracket camera__bracket--tr" aria-hidden />
        <div className="camera__bracket camera__bracket--bl" aria-hidden />
        <div className="camera__bracket camera__bracket--br" aria-hidden />

        {/* Video */}
        <video
          ref={videoRef}
          className="camera__video"
          playsInline
          muted
          autoPlay
        />

        {/* Skeleton overlay */}
        <canvas ref={canvasRef} className="camera__canvas" />

        {/* Hint shown when no person detected */}
        {showHint && (
          <div className="camera__hint">
            <div className="camera__hint-pulse" aria-hidden />
            <span className="label">stand in frame</span>
          </div>
        )}
      </div>
    );
  }
);
