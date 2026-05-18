/* ============================================================
 * PhysioAI Pro V2 — useVoiceGuidance
 * ============================================================
 * English TTS for exercise guidance (separate from the Arabic
 * coaching via useArabicVoice).
 *
 * Uses the Web Speech API with lang 'en-US'.
 * speak() cancels any in-flight utterance before starting the
 * new one, so instructions never queue or stack.
 * ============================================================ */

import { useCallback, useRef, useState } from "react";

export function useVoiceGuidance() {
  const [speaking, setSpeaking] = useState(false);
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);

  const speak = useCallback((text: string) => {
    if (!("speechSynthesis" in window)) return;

    // Cancel whatever is currently playing.
    window.speechSynthesis.cancel();
    setSpeaking(false);

    if (!text.trim()) return;

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = "en-US";
    utterance.rate = 0.92;
    utterance.pitch = 1.0;

    utterance.onstart = () => setSpeaking(true);
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);

    utteranceRef.current = utterance;
    window.speechSynthesis.speak(utterance);
  }, []);

  return { speak, speaking };
}
