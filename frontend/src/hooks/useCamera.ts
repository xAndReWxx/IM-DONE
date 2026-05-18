/* ============================================================
 * PhysioAI Pro V2 — useCamera
 * ============================================================
 * Opens the user-facing camera, wires its MediaStream to a
 * <video> element, and gives the caller `start`/`stop` controls.
 *
 * BUG FIX (camera init race):
 *   The previous version called video.play() immediately after
 *   setting srcObject, which could be interrupted by a second
 *   call before the browser had finished loading. The fix:
 *     1. Stop any existing stream before starting a new one.
 *     2. Wait for the `canplay` event (or readyState >= 2)
 *        before calling play().
 *     3. Handle AbortError gracefully (play interrupted = not
 *        a real error if we triggered it ourselves).
 *     4. Use a playingRef to prevent concurrent play() calls.
 * ============================================================ */

import { useCallback, useRef, useState } from "react";

export function useCamera() {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [active, setActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Guards against two simultaneous play() attempts.
  const playingRef = useRef(false);

  /** Request camera permission and start the stream. */
  const start = useCallback(async () => {
    setError(null);

    const video = videoRef.current;

    // Stop any previously active stream first.
    const oldStream = video?.srcObject as MediaStream | null;
    if (oldStream) {
      oldStream.getTracks().forEach((t) => t.stop());
      if (video) video.srcObject = null;
    }

    // Don't start again if already playing.
    if (playingRef.current) return;
    playingRef.current = true;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: "user",
          width: { ideal: 640 },
          height: { ideal: 480 },
        },
        audio: false,
      });

      if (!video) {
        // videoRef not yet attached — tear down the stream and bail.
        stream.getTracks().forEach((t) => t.stop());
        playingRef.current = false;
        return;
      }

      video.srcObject = stream;

      // Wait until the browser has decoded enough to play without stalling.
      await waitUntilCanPlay(video);

      try {
        await video.play();
      } catch (e) {
        // AbortError means play() was interrupted (e.g. srcObject replaced).
        // This is benign — the stream is still live; don't surface it as an error.
        if (e instanceof DOMException && e.name === "AbortError") {
          playingRef.current = false;
          return;
        }
        throw e; // Re-throw anything else.
      }

      setActive(true);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Camera unavailable";
      setError(msg);
      setActive(false);
    } finally {
      playingRef.current = false;
    }
  }, []);

  /** Stop the stream and clear the video element. */
  const stop = useCallback(() => {
    const video = videoRef.current;
    const stream = video?.srcObject as MediaStream | null;
    stream?.getTracks().forEach((t) => t.stop());
    if (video) {
      video.pause();
      video.srcObject = null;
    }
    setActive(false);
  }, []);

  return { videoRef, active, error, start, stop };
}

/* ── Helpers ── */

/**
 * Resolve when the video element has enough data to start playback.
 * Uses the `canplay` event but falls back immediately if the browser
 * already reports readyState >= 2 (HAVE_CURRENT_DATA).
 */
function waitUntilCanPlay(video: HTMLVideoElement): Promise<void> {
  return new Promise((resolve) => {
    if (video.readyState >= 2) {
      resolve();
      return;
    }
    const onCanPlay = () => {
      video.removeEventListener("canplay", onCanPlay);
      resolve();
    };
    video.addEventListener("canplay", onCanPlay);
  });
}
