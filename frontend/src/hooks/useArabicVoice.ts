/* ============================================================
 * PhysioAI Pro V2 — useArabicVoice
 * ============================================================
 * Speaks short Arabic coaching lines using the browser's built-in
 * Web Speech API. No external TTS service needed.
 *
 * BEHAVIOR
 *   • Same line is never read twice in a row (lastSpoken guard)
 *   • A small debounce stops rapid-fire utterances
 *   • Skipping is graceful if the browser has no Arabic voice —
 *     the caller can disable the hook entirely via the `enabled`
 *     flag (mic-mute toggle in the UI)
 * ============================================================ */

import { useCallback, useEffect, useRef } from "react";

export function useArabicVoice(enabled: boolean) {
  const lastSpokenRef = useRef("");
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /** Queue up an Arabic line for TTS. Deduplicated and debounced. */
  const speak = useCallback((text: string) => {
    if (!enabled || !text) return;
    if (text === lastSpokenRef.current) return;
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;

    lastSpokenRef.current = text;
    window.speechSynthesis.cancel();
    if (timeoutRef.current) clearTimeout(timeoutRef.current);

    // 400ms debounce keeps the voice from stuttering when the
    // backend rapidly toggles between issues.
    timeoutRef.current = setTimeout(() => {
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = "ar-SA";
      utterance.rate = 0.9;
      utterance.pitch = 1.05;
      window.speechSynthesis.speak(utterance);
    }, 400);
  }, [enabled]);

  // Cancel any pending speech on unmount or when disabled.
  useEffect(() => {
    return () => {
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  return { speak };
}
