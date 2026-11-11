"use client";

import type { SpeakInput, VoiceCallbacks, VoiceProvider, VoiceUsage } from "./types";

/* eslint-disable @typescript-eslint/no-explicit-any -- Web Speech API typings are not in lib.dom */
type Recognition = any;

function getRecognitionCtor(): (new () => Recognition) | null {
  if (typeof window === "undefined") return null;
  const w = window as any;
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

function splitSentences(text: string): string[] {
  // Chrome cuts long utterances; speak sentence-sized chunks.
  return text.match(/[^.!?]+[.!?]*\s*/g)?.map((s) => s.trim()).filter(Boolean) ?? [text];
}

const PREFERRED_VOICES = [/Google US English/i, /Microsoft (Aria|Jenny|Guy).*Natural/i, /Samantha/i, /Google UK English Female/i, /en-US/i];

/**
 * Pick an on-device speech voice. Prefers the session language (e.g. en-IN), then known good
 * voices. `localOnly` skips network voices such as "Google US English", which are silent offline.
 */
export function pickSpeechVoice(voices: SpeechSynthesisVoice[], lang: string, localOnly: boolean): SpeechSynthesisVoice | undefined {
  const pool = localOnly ? voices.filter((v) => v.localService) : voices;
  const byLang = pool.filter((v) => v.lang.replace("_", "-").toLowerCase() === lang.toLowerCase());
  if (byLang.length) return byLang.find((v) => /natural|neural/i.test(v.name)) ?? byLang[0];
  return PREFERRED_VOICES.map((re) => pool.find((v) => re.test(v.name) || re.test(v.lang))).find(Boolean) ?? pool.find((v) => v.lang.startsWith("en"));
}

/** Web Speech API provider: free, on-device/browser-vendor STT + TTS. Best in Chrome and Edge. */
export class BrowserVoiceProvider implements VoiceProvider {
  readonly name: string = "browser";
  readonly sttSupported = getRecognitionCtor() !== null;

  protected cb: VoiceCallbacks | null = null;
  private recognition: Recognition | null = null;
  private active = false;
  private muted = false;
  protected speaking = false;
  private finalBuffer = "";
  private interim = "";
  private silenceTimer: ReturnType<typeof setTimeout> | null = null;
  private silenceMs = 3500;
  private listenStartedAt = 0;
  private listenedMs = 0;
  private lastSpeechEnd = 0;
  private latencies: number[] = [];
  private stream: MediaStream | null = null;
  private audioCtx: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private raf = 0;
  private loudFrames = 0;
  private interruptResolve: (() => void) | null = null;
  private bargeIn = false;
  private sttFailures = 0;
  private restartDelay = 150;

  /** `lang` is the recognition locale, e.g. en-IN when the server voice is Indian English. */
  constructor(protected readonly lang: string = "en-US") {}

  prime(): void {
    // A silent utterance inside the click unlocks speech output (required on Safari/iOS).
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    try {
      const u = new SpeechSynthesisUtterance(" ");
      u.volume = 0;
      window.speechSynthesis.speak(u);
    } catch {
      /* best effort */
    }
  }

  async connect(callbacks: VoiceCallbacks, options: { listen?: boolean } = {}): Promise<boolean> {
    this.cb = callbacks;
    if (options.listen === false) return true;
    if (this.stream) return this.sttSupported;
    if (!navigator.mediaDevices?.getUserMedia) {
      callbacks.onError("unsupported", "This browser can't access a microphone.");
      callbacks.onState("unsupported");
      return false;
    }
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
    } catch (e) {
      const name = (e as DOMException).name;
      callbacks.onError(
        name === "NotFoundError" ? "no_mic" : "mic_denied",
        name === "NotFoundError" ? "No microphone was found." : "Microphone permission was denied.",
      );
      callbacks.onState("disconnected");
      return false;
    }
    this.startLevelMeter();
    if (!this.sttSupported) {
      callbacks.onError("unsupported", "Speech recognition isn't available in this browser. Use Chrome or Edge, or type your answers.");
      callbacks.onState("unsupported");
      return false;
    }
    return true;
  }

  private startLevelMeter() {
    if (!this.stream) return;
    try {
      this.audioCtx = new AudioContext();
      const src = this.audioCtx.createMediaStreamSource(this.stream);
      this.analyser = this.audioCtx.createAnalyser();
      this.analyser.fftSize = 512;
      src.connect(this.analyser);
      const buf = new Uint8Array(this.analyser.fftSize);
      const tick = () => {
        if (!this.analyser) return;
        this.analyser.getByteTimeDomainData(buf);
        let sum = 0;
        for (const v of buf) sum += ((v - 128) / 128) ** 2;
        const level = Math.min(1, Math.sqrt(sum / buf.length) * 4);
        this.cb?.onLevel?.(this.muted ? 0 : level);
        // Barge-in: sustained candidate speech while the interviewer is talking.
        if (this.speaking && !this.muted && this.bargeIn) {
          this.loudFrames = level > 0.35 ? this.loudFrames + 1 : Math.max(0, this.loudFrames - 1);
          if (this.loudFrames > 12) {
            this.loudFrames = 0;
            this.cb?.onBargeIn();
            this.stopSpeaking();
          }
        }
        this.raf = requestAnimationFrame(tick);
      };
      this.raf = requestAnimationFrame(tick);
    } catch {
      /* level meter is cosmetic */
    }
  }

  startSession(): void {
    this.active = true;
    if (!this.speaking) this.listen();
  }

  sendAudio(): void {
    /* browser recognition captures audio itself */
  }

  private listen() {
    if (!this.active || this.muted || this.speaking || this.recognition) return;
    const Ctor = getRecognitionCtor();
    if (!Ctor) return;
    const rec: Recognition = new Ctor();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = this.lang;
    rec.maxAlternatives = 1;
    rec.onstart = () => {
      this.listenStartedAt = performance.now();
      this.cb?.onState("listening");
    };
    rec.onspeechend = () => {
      this.lastSpeechEnd = performance.now();
    };
    rec.onresult = (ev: any) => {
      this.sttFailures = 0;
      this.restartDelay = 150;
      let interim = "";
      for (let i = ev.resultIndex; i < ev.results.length; i++) {
        const r = ev.results[i];
        if (r.isFinal) {
          this.finalBuffer = `${this.finalBuffer} ${r[0].transcript}`.trim();
          if (this.lastSpeechEnd) this.latencies.push(performance.now() - this.lastSpeechEnd);
        } else interim += r[0].transcript;
      }
      this.interim = interim;
      this.cb?.onPartial(`${this.finalBuffer} ${interim}`.trim());
      this.armSilence();
    };
    rec.onerror = (ev: any) => {
      if (ev.error === "not-allowed" || ev.error === "service-not-allowed") {
        this.cb?.onError("mic_denied", "Microphone permission was denied for speech recognition.");
        this.active = false;
      } else if (ev.error === "audio-capture") {
        this.cb?.onError("no_mic", "The microphone isn't capturing audio.");
        this.active = false;
      } else if (ev.error === "network" || ev.error === "language-not-supported") {
        // Chrome's recognition runs on a cloud service: without internet it fails on every restart.
        this.sttFailures += 1;
        this.restartDelay = Math.min(4000, this.restartDelay * 2);
        if (this.sttFailures >= 2) {
          this.active = false;
          this.cb?.onError(
            "stt_unavailable",
            ev.error === "network"
              ? "Speech recognition needs an internet connection and couldn't reach it."
              : `Speech recognition doesn't support ${this.lang} in this browser.`,
          );
        }
      } else if (ev.error !== "no-speech" && ev.error !== "aborted") {
        this.cb?.onError("stt_error", "Speech recognition hiccup — still listening.");
      }
    };
    rec.onend = () => {
      if (this.listenStartedAt) this.listenedMs += performance.now() - this.listenStartedAt;
      this.listenStartedAt = 0;
      // stopListening() may already have replaced this instance; don't clobber a newer one.
      if (this.recognition === rec) this.recognition = null;
      // Chrome stops continuous recognition periodically; resume while the session is live.
      if (this.active && !this.muted && !this.speaking) setTimeout(() => this.listen(), this.restartDelay);
    };
    this.recognition = rec;
    try {
      rec.start();
    } catch {
      this.recognition = null;
    }
  }

  private armSilence() {
    if (this.silenceTimer) clearTimeout(this.silenceTimer);
    this.silenceTimer = setTimeout(() => this.flush(), this.silenceMs);
  }

  private flush() {
    if (this.silenceTimer) clearTimeout(this.silenceTimer);
    this.silenceTimer = null;
    const text = `${this.finalBuffer} ${this.interim}`.trim();
    this.finalBuffer = "";
    this.interim = "";
    if (text) {
      this.cb?.onFinal(text);
      this.cb?.onState("thinking");
    }
  }

  commitAnswer(): void {
    this.flush();
  }

  private stopListening() {
    if (this.silenceTimer) clearTimeout(this.silenceTimer);
    const rec = this.recognition;
    this.recognition = null;
    try {
      rec?.abort();
    } catch {
      /* noop */
    }
  }

  async speak(input: SpeakInput): Promise<"done" | "interrupted"> {
    const text = input.segments.join(" ").trim();
    if (!text) return "done";
    // Don't capture the interviewer's own voice as an answer.
    this.stopListening();
    this.finalBuffer = "";
    this.interim = "";
    this.speaking = true;
    this.cb?.onState("speaking");
    let result: "done" | "interrupted" = "done";
    try {
      result = await this.speakText(text, input);
    } finally {
      this.speaking = false;
    }
    if (this.active && !this.muted) {
      this.cb?.onState("listening");
      this.listen();
    } else this.cb?.onState(this.muted ? "muted" : "idle");
    return result;
  }

  protected speakText(text: string, _input: SpeakInput): Promise<"done" | "interrupted"> {
    return new Promise((resolve) => {
      if (typeof window === "undefined" || !("speechSynthesis" in window)) {
        this.cb?.onError("tts_error", "Speech output isn't available; questions are shown on screen.");
        resolve("done");
        return;
      }
      const synth = window.speechSynthesis;
      if (synth.speaking || synth.pending) synth.cancel();
      const voices = synth.getVoices();
      let localOnly = typeof navigator !== "undefined" && !navigator.onLine;
      let voice = pickSpeechVoice(voices, this.lang, localOnly);
      const parts = splitSentences(text);
      let i = 0;
      let finished = false;
      const done = (r: "done" | "interrupted") => {
        if (finished) return;
        finished = true;
        clearTimeout(safety);
        this.interruptResolve = null;
        resolve(r);
      };
      this.interruptResolve = () => done("interrupted");
      const say = (part: string) => {
        const u = new SpeechSynthesisUtterance(part);
        if (voice) u.voice = voice;
        u.lang = voice?.lang ?? this.lang;
        u.rate = 1.02;
        u.pitch = 1;
        u.onend = next;
        u.onerror = (ev) => {
          if (ev.error === "interrupted" || ev.error === "canceled") return;
          // A network voice fails offline: retry this sentence once with an on-device voice.
          if (!localOnly && voice && !voice.localService) {
            localOnly = true;
            voice = pickSpeechVoice(voices, this.lang, true);
            say(part);
          } else next();
        };
        synth.speak(u);
      };
      const next = () => {
        if (finished) return;
        if (i >= parts.length) return done("done");
        say(parts[i++]);
      };
      // Safety net: never block the interview on a stuck synthesiser.
      const safety = setTimeout(() => done("done"), Math.max(8000, text.length * 110));
      next();
    });
  }

  stopSpeaking(): void {
    if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel();
    this.interruptResolve?.();
  }

  setMuted(muted: boolean): void {
    if (muted === this.muted) return;
    this.muted = muted;
    if (muted) {
      this.stopListening();
      this.cb?.onState("muted");
    } else {
      this.cb?.onState(this.speaking ? "speaking" : "listening");
      this.listen();
    }
  }

  setSilenceMs(ms: number): void {
    this.silenceMs = ms;
  }

  setBargeIn(enabled: boolean): void {
    this.bargeIn = enabled;
  }

  /** Re-enable recognition after it was stopped (e.g. the candidate switches back to voice). */
  resumeListening(): void {
    this.sttFailures = 0;
    this.restartDelay = 150;
    if (this.stream && this.sttSupported) this.startSession();
  }

  stopSession(): void {
    this.active = false;
    this.stopListening();
    this.stopSpeaking();
    cancelAnimationFrame(this.raf);
    this.analyser = null;
    void this.audioCtx?.close().catch(() => undefined);
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    this.cb?.onState("disconnected");
  }

  usage(): VoiceUsage {
    const live = this.listenStartedAt ? performance.now() - this.listenStartedAt : 0;
    const avg = this.latencies.length ? this.latencies.reduce((a, b) => a + b, 0) / this.latencies.length : 0;
    return { sttSeconds: (this.listenedMs + live) / 1000, avgLatencyMs: Math.round(avg) };
  }
}
