/**
 * Client-side voice abstraction. Business logic (the interview room) only talks to this
 * interface; vendors live behind it. The server decides which implementation to use via the
 * VoiceSessionConfig returned with the WebSocket ticket.
 */
export type VoiceState = "idle" | "listening" | "thinking" | "speaking" | "muted" | "disconnected" | "unsupported";

export interface VoiceCallbacks {
  /** Live (unstable) transcript of what the candidate is saying. */
  onPartial: (text: string) => void;
  /** A complete answer, emitted after the candidate pauses or presses "Done". */
  onFinal: (text: string) => void;
  /** Candidate started talking while the interviewer was speaking (barge-in). */
  onBargeIn: () => void;
  onState: (state: VoiceState) => void;
  /** `stt_unavailable`: recognition keeps failing (usually no internet); the room switches to typing. */
  onError: (code: "mic_denied" | "no_mic" | "stt_error" | "stt_unavailable" | "tts_error" | "unsupported", message: string) => void;
  /** Normalised microphone level 0..1 for the waveform. */
  onLevel?: (level: number) => void;
}

export interface SpeakInput {
  segments: string[];
  audio?: { mime_type: string; b64: string };
}

export interface VoiceUsage {
  sttSeconds: number;
  avgLatencyMs: number;
}

export interface VoiceProvider {
  readonly name: string;
  readonly sttSupported: boolean;
  /**
   * Unlock audio output. Call synchronously inside the click that starts the interview: browsers
   * only allow sound that is started from a user gesture.
   */
  prime(): void;
  /** Attach callbacks. With `listen: false` only the interviewer's voice is used (typed answers). */
  connect(callbacks: VoiceCallbacks, options?: { listen?: boolean }): Promise<boolean>;
  startSession(): void;
  /** Streaming providers forward raw audio; the browser provider records natively and ignores this. */
  sendAudio(chunk: ArrayBuffer): void;
  /** Ask the provider to finalise the current answer now (the "Done answering" button). */
  commitAnswer(): void;
  speak(input: SpeakInput): Promise<"done" | "interrupted">;
  stopSpeaking(): void;
  setMuted(muted: boolean): void;
  /** Restart recognition after it stopped on errors (candidate switched back to voice). */
  resumeListening(): void;
  setSilenceMs(ms: number): void;
  /** Voice-activated interruption. Off by default: speaker echo can trigger it without headphones. */
  setBargeIn(enabled: boolean): void;
  stopSession(): void;
  usage(): VoiceUsage;
}
