"use client";

import type { VoiceSessionConfig } from "@intervue/types";

import { BrowserVoiceProvider } from "./browser";
import type { SpeakInput, VoiceProvider } from "./types";

// 0.05 s of silence: played inside the start click so later (non-gesture) playback is allowed.
const SILENT_WAV = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQAAAAA=";

/** Server-side TTS (Edge, ElevenLabs): plays audio returned with AI_SPEAKING; STT stays in-browser. */
class ServerTtsVoiceProvider extends BrowserVoiceProvider {
  override readonly name = "server-tts";
  private audio: HTMLAudioElement | null = null;
  private stopCurrent: (() => void) | null = null;

  private element(): HTMLAudioElement {
    if (!this.audio) {
      this.audio = new Audio();
      this.audio.preload = "auto";
    }
    return this.audio;
  }

  override prime(): void {
    super.prime();
    const el = this.element();
    el.src = SILENT_WAV;
    void el.play().catch(() => undefined);
  }

  protected override speakText(text: string, input: SpeakInput): Promise<"done" | "interrupted"> {
    if (!input.audio) return super.speakText(text, input);
    const src = `data:${input.audio.mime_type};base64,${input.audio.b64}`;
    return new Promise((resolve) => {
      const el = this.element();
      let settled = false;
      let safety: ReturnType<typeof setTimeout> | undefined;
      const cleanup = () => {
        clearTimeout(safety);
        el.onended = el.onerror = el.onloadedmetadata = null;
        this.stopCurrent = null;
      };
      const finish = (r: "done" | "interrupted") => {
        if (settled) return;
        settled = true;
        cleanup();
        resolve(r);
      };
      const fallback = (message: string) => {
        if (settled) return;
        settled = true;
        cleanup();
        this.cb?.onError("tts_error", message);
        void super.speakText(text, input).then(resolve);
      };
      // Never block the interview on audio that doesn't finish; refined once the duration is known.
      const arm = (ms: number) => {
        clearTimeout(safety);
        safety = setTimeout(() => finish("done"), ms);
      };
      arm(Math.max(10000, text.length * 120));
      el.onloadedmetadata = () => {
        if (Number.isFinite(el.duration) && el.duration > 0) arm(el.duration * 1000 + 2500);
      };
      el.onended = () => finish("done");
      el.onerror = () => fallback("Couldn't play the interviewer's voice; using on-device speech.");
      this.stopCurrent = () => {
        el.pause();
        finish("interrupted");
      };
      el.src = src;
      el.play().catch((e: DOMException) =>
        fallback(
          e?.name === "NotAllowedError"
            ? "Your browser blocked audio playback. Click anywhere on the page to allow sound; using on-device speech for now."
            : "Couldn't play the interviewer's voice; using on-device speech.",
        ),
      );
    });
  }

  override stopSpeaking(): void {
    this.stopCurrent?.();
    super.stopSpeaking();
  }
}

export function createVoiceProvider(config: VoiceSessionConfig | null): VoiceProvider {
  const lang = config?.language || "en-US";
  if (config?.tts === "server") return new ServerTtsVoiceProvider(lang);
  return new BrowserVoiceProvider(lang);
}

export { pickSpeechVoice } from "./browser";
export type { VoiceProvider, VoiceState, VoiceCallbacks } from "./types";
