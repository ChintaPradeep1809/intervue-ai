"use client";

import type { InterviewDetail, LiveState, SpeechSegment, WsEvent } from "@intervue/types";
import {
  CheckCircle2,
  Code2,
  Headphones,
  Keyboard,
  Loader2,
  Mic,
  MicOff,
  MonitorOff,
  MonitorUp,
  Network,
  PhoneOff,
  Send,
  SkipForward,
  Square,
  Video,
  VideoOff,
  Wifi,
  WifiOff,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Logo } from "@/components/brand/logo";
import { CodeWorkspace } from "@/components/coding/code-workspace";
import { ProblemPanel } from "@/components/coding/problem-panel";
import { DesignCanvas } from "@/components/design/design-canvas";
import { Waveform } from "@/components/interview/waveform";
import { MockNotice } from "@/components/shared/primitives";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { formatDuration } from "@/lib/format";
import { useInterviewSocket } from "@/lib/use-interview-socket";
import { useScreenShare } from "@/lib/use-screen-share";
import { cn } from "@/lib/utils";
import { createVoiceProvider, type VoiceCallbacks, type VoiceProvider, type VoiceState } from "@/lib/voice";

interface Line {
  id: number;
  speaker: "interviewer" | "candidate";
  text: string;
}

const STATE_LABEL: Record<VoiceState | "typing", string> = {
  idle: "Ready",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
  muted: "Muted",
  disconnected: "Disconnected",
  unsupported: "Voice unavailable",
  typing: "Waiting for your typed answer",
};

function ControlButton({
  label,
  onClick,
  active,
  danger,
  disabled,
  children,
}: {
  label: string;
  onClick: () => void;
  active?: boolean;
  danger?: boolean;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <button
            onClick={onClick}
            disabled={disabled}
            aria-label={label}
            aria-pressed={active}
            className={cn(
              "grid size-11 place-items-center rounded-full transition-colors disabled:opacity-40",
              danger ? "bg-destructive text-white hover:bg-destructive/90" : active ? "bg-white/90 text-studio" : "bg-white/10 text-studio-foreground hover:bg-white/20",
            )}
          />
        }
      >
        {children}
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

export function InterviewRoom({ interview }: { interview: InterviewDetail }) {
  const router = useRouter();
  const id = interview.id;
  const [live, setLive] = useState<LiveState>(interview.live);
  const [lines, setLines] = useState<Line[]>([]);
  const [partial, setPartial] = useState("");
  const [voiceState, setVoiceState] = useState<VoiceState>("idle");
  const [level, setLevel] = useState(0);
  const [caption, setCaption] = useState<string>("");
  const [thinking, setThinking] = useState(false);
  const [joined, setJoined] = useState(false);
  const [typed, setTyped] = useState("");
  const [typeMode, setTypeMode] = useState(false);
  const [muted, setMuted] = useState(false);
  const [bargeIn, setBargeIn] = useState(false);
  const [confirmEnd, setConfirmEnd] = useState(false);
  const [completed, setCompleted] = useState(interview.status === "completed");
  const [ending, setEnding] = useState(interview.status === "evaluating");
  const [now, setNow] = useState(() => Date.now() / 1000);
  const [cameraOn, setCameraOn] = useState(false);
  const offset = useRef(0);
  const voice = useRef<VoiceProvider | null>(null);
  const micReady = useRef(false);
  const speechChain = useRef<Promise<unknown>>(Promise.resolve());
  const lineId = useRef(0);
  const liveRef = useRef(live);
  const camRef = useRef<HTMLVideoElement>(null);
  const camStream = useRef<MediaStream | null>(null);
  const screen = useScreenShare(id);
  const screenRef = useRef(screen);
  const prefs = useMemo(() => {
    if (typeof window === "undefined") return { voice: true, camera: false };
    try {
      return JSON.parse(sessionStorage.getItem(`iv-prefs-${id}`) ?? "") as { voice: boolean; camera: boolean };
    } catch {
      return { voice: true, camera: false };
    }
  }, [id]);

  useEffect(() => {
    liveRef.current = live;
  }, [live]);
  useEffect(() => {
    screenRef.current = screen;
  }, [screen]);

  const addLine = useCallback((speaker: Line["speaker"], text: string) => {
    lineId.current += 1;
    const lid = lineId.current;
    setLines((ls) => [...ls.slice(-60), { id: lid, speaker, text }]);
  }, []);

  const speak = useCallback((segments: SpeechSegment[], audio?: { mime_type: string; b64: string }) => {
    const text = segments.map((s) => s.text).join(" ");
    speechChain.current = speechChain.current.then(async () => {
      setCaption(text);
      setThinking(false);
      if (voice.current) await voice.current.speak({ segments: segments.map((s) => s.text), audio });
    });
  }, []);

  const onEvent = useCallback(
    (e: WsEvent) => {
      const p = e.payload as Record<string, unknown>;
      switch (e.event_type) {
        case "STATE_SYNC": {
          const s = p as unknown as LiveState;
          offset.current = s.server_time - Date.now() / 1000;
          setLive(s);
          if (s.next_action !== "WAIT_FOR_ANSWER" || s.question) setThinking(false);
          if (s.status === "completed") setCompleted(true);
          if (s.status === "evaluating") setEnding(true);
          break;
        }
        case "AI_SPEAKING": {
          const segs = (p.segments as SpeechSegment[]) ?? [];
          segs.forEach((s) => addLine("interviewer", s.text));
          if (p.tts_error) toast.message(String(p.tts_error));
          speak(segs, p.audio as { mime_type: string; b64: string } | undefined);
          break;
        }
        case "AI_THINKING":
          setThinking(true);
          break;
        case "TRANSCRIPT_FINAL":
          addLine("candidate", String(p.text));
          setPartial("");
          break;
        case "CODING_STARTED":
          toast.message("Coding round started — the problem is on the left, the editor on the right.");
          break;
        case "CODE_REVIEW_STARTED":
          if (screenRef.current.state === "sharing") {
            void screenRef.current.snapshot("code_review").then((ok) => ok && toast.message("A snapshot of your screen was shared with the interviewer."));
          }
          break;
        case "SCREEN_SHARE_STARTED":
          toast.success("Screen sharing enabled");
          break;
        case "SCREEN_SHARE_STOPPED":
          toast.message("Screen sharing stopped");
          break;
        case "INTERVIEW_ENDING":
          setEnding(true);
          break;
        case "INTERVIEW_COMPLETED":
          setCompleted(true);
          break;
        case "ERROR":
          setThinking(false);
          toast.error(String(p.message ?? "Something went wrong."));
          break;
      }
    },
    [addLine, speak],
  );

  const { status: conn, send, voice: voiceConfig } = useInterviewSocket(id, onEvent);

  // clock
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now() / 1000), 500);
    return () => clearInterval(t);
  }, []);

  // report voice usage + stop media when the interview ends or the page unloads
  const shutdown = useCallback(() => {
    const v = voice.current;
    if (v) {
      const u = v.usage();
      send("VOICE_USAGE", { stt_seconds: u.sttSeconds, avg_latency_ms: u.avgLatencyMs, provider: voiceConfig?.provider ?? "browser" });
      v.stopSession();
      voice.current = null;
    }
    camStream.current?.getTracks().forEach((t) => t.stop());
    screenRef.current.stop();
  }, [send, voiceConfig]);

  useEffect(() => {
    if (completed) {
      void speechChain.current.then(() => shutdown());
    }
  }, [completed, shutdown]);

  useEffect(() => () => {
    voice.current?.stopSession();
    camStream.current?.getTracks().forEach((t) => t.stop());
  }, []);

  const voiceCallbacks: VoiceCallbacks = {
    onPartial: (t) => {
      setPartial(t);
      send("TRANSCRIPT_PARTIAL", { text: t });
    },
    onFinal: (t) => {
      const s = liveRef.current;
      if (s.next_action === "WAIT_FOR_ANSWER") {
        send("ANSWER", { text: t, source: "voice" });
        setThinking(true);
      } else if (s.next_action === "WAIT_FOR_CODE") {
        toast.message("Keep thinking aloud — submit your code when you're ready and the interviewer will review it.");
      } else {
        // never drop what the candidate said: offer it for editing and sending
        setTyped(t);
        toast.message("The interviewer wasn't ready for an answer yet.", {
          action: { label: "Edit & send", onClick: () => setTypeMode(true) },
        });
      }
      setPartial("");
    },
    onBargeIn: () => setCaption((c) => c),
    onState: setVoiceState,
    onError: (code, message) => {
      if (code === "mic_denied" || code === "unsupported" || code === "no_mic" || code === "stt_unavailable") {
        setTypeMode(true);
        toast.error(`${message} Switched to typed answers — the interviewer still speaks.`);
      } else toast.message(message);
    },
    onLevel: setLevel,
  };

  async function enableMic(v: VoiceProvider): Promise<boolean> {
    const ok = await v.connect(voiceCallbacks, { listen: true });
    if (ok) {
      v.startSession();
      micReady.current = true;
      send("VOICE_SESSION_STARTED", { provider: voiceConfig?.provider ?? "browser" });
    }
    return ok;
  }

  async function join() {
    setJoined(true);
    const wantVoice = prefs.voice !== false;
    // The interviewer always speaks, also when answers are typed.
    const v = createVoiceProvider(voiceConfig);
    voice.current = v;
    v.prime(); // must run synchronously inside this click so later audio may play
    await v.connect(voiceCallbacks, { listen: false });
    if (!wantVoice || !(await enableMic(v))) setTypeMode(true);
    if (prefs.camera) void toggleCamera();
    if (liveRef.current.next_action === "START") send("START");
    else if (liveRef.current.question) {
      toast.message("Interview resumed");
      speak([{ text: `Welcome back. Here's where we left off. ${liveRef.current.question.text}`, kind: "info" }]);
    }
  }

  async function toggleCamera() {
    if (camStream.current) {
      camStream.current.getTracks().forEach((t) => t.stop());
      camStream.current = null;
      setCameraOn(false);
      return;
    }
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: { width: 320, height: 240 } });
      camStream.current = s;
      setCameraOn(true);
      requestAnimationFrame(() => {
        if (camRef.current) camRef.current.srcObject = s;
      });
    } catch {
      toast.error("Camera permission was denied.");
    }
  }

  function submitTyped() {
    const t = typed.trim();
    if (!t || live.next_action !== "WAIT_FOR_ANSWER") return;
    send("ANSWER", { text: t, source: "typed" });
    setTyped("");
    setThinking(true);
  }

  async function switchMode() {
    if (!typeMode) {
      // keep whatever was already recognised so it can be edited and sent
      if (partial) setTyped((t) => (t ? `${t} ${partial}` : partial));
      setPartial("");
      setTypeMode(true);
      return;
    }
    const v = voice.current;
    if (!v) return;
    if (micReady.current) v.resumeListening();
    else if (!(await enableMic(v))) return;
    setTypeMode(false);
  }

  function toggleMute() {
    setMuted((m) => !m); // applied to the provider by the effect below
  }

  // the microphone doesn't listen while the candidate types (no duplicate answers)
  useEffect(() => {
    voice.current?.setMuted(muted || typeMode);
  }, [muted, typeMode]);

  // keyboard: Space = done answering (when not typing), Esc = interrupt interviewer
  useEffect(() => {
    if (!joined) return;
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const inField = target.closest("textarea, input, select, .monaco-editor, [contenteditable=true]");
      if (e.key === "Escape") voice.current?.stopSpeaking();
      if (e.code === "Space" && !inField && voiceState === "listening" && partial) {
        e.preventDefault();
        voice.current?.commitAnswer();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [joined, voiceState, partial]);

  const remaining = live.deadline_at ? live.deadline_at - (now + offset.current) : interview.plan.duration_minutes * 60;
  const isCoding = !!live.coding && (live.phase === "CODING" || live.phase === "CODE_REVIEW");
  const isDesign = live.design_active;
  const presence: VoiceState | "typing" = thinking ? "thinking" : typeMode && voiceState !== "speaking" ? "typing" : voiceState;
  const waitingAnswer = live.next_action === "WAIT_FOR_ANSWER";
  const currentRound = live.rounds[live.round_index];

  // ---------------------------------------------------------------- completed / evaluating
  if (completed || ending) {
    return (
      <div className="grid min-h-screen place-items-center bg-studio px-4 text-studio-foreground">
        <div className="w-full max-w-md space-y-6 text-center">
          {completed ? <CheckCircle2 className="mx-auto size-12 text-success" /> : <Loader2 className="mx-auto size-12 animate-spin text-primary" />}
          <div>
            <h1 className="text-2xl font-semibold">{completed ? "Your evaluation is ready" : "Preparing your evaluation"}</h1>
            <p className="mt-2 text-sm text-studio-foreground/70">
              {completed
                ? "Scores, evidence from your answers and a personalised practice plan."
                : "Scoring each answer against the evidence and building your practice plan…"}
            </p>
          </div>
          {completed && (
            <div className="flex flex-col gap-2">
              <Button className="h-11" onClick={() => router.push(`/interviews/${id}/report`)}>
                View report
              </Button>
              {interview.is_demo && (
                <Link href="/auth/register" className="text-sm text-studio-foreground/70 underline underline-offset-4">
                  Create your full interview
                </Link>
              )}
            </div>
          )}
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------- join overlay
  if (!joined) {
    const resuming = live.next_action !== "START";
    return (
      <div className="grid min-h-screen place-items-center bg-studio px-4 text-studio-foreground">
        <div className="w-full max-w-lg space-y-6 text-center">
          <Logo inverted href="/dashboard" className="justify-center" />
          <div>
            <h1 className="text-2xl font-semibold">{interview.title}</h1>
            <p className="mt-2 text-sm text-studio-foreground/70">
              {interview.plan.duration_minutes} minutes · {interview.plan.rounds.map((r) => r.title).join(" → ")}
            </p>
          </div>
          <div className="mx-auto max-w-sm space-y-2 rounded-xl bg-white/5 p-4 text-left text-sm text-studio-foreground/80 ring-1 ring-white/10">
            <p>• The interviewer speaks each question; it is also shown on screen.</p>
            <p>• Answer out loud. Your answer is sent when you pause — or press <kbd className="rounded bg-white/15 px-1">Space</kbd>.</p>
            <p>• Say “could you repeat that?” anytime. Press <kbd className="rounded bg-white/15 px-1">Esc</kbd> to interrupt.</p>
          </div>
          <Button className="h-12 w-full max-w-sm text-base" onClick={join} disabled={conn !== "connected"}>
            {conn !== "connected" ? <Loader2 className="size-4 animate-spin" /> : null}
            {conn !== "connected" ? "Connecting…" : resuming ? "Resume interview" : "Start interview"}
          </Button>
          <MockNotice show={live.ai_is_mock} className="border-white/20 text-studio-foreground/60" />
        </div>
      </div>
    );
  }

  // ---------------------------------------------------------------- room
  const presencePanel = (
    <div className={cn("flex items-center gap-4", isCoding || isDesign ? "" : "flex-col text-center")}>
      <div
        className={cn(
          "relative grid shrink-0 place-items-center rounded-full bg-primary/20 ring-1 ring-primary/40",
          isCoding || isDesign ? "size-12" : "size-28",
          voiceState === "speaking" && "animate-pulse-ring",
        )}
      >
        <span className={cn("font-semibold", isCoding || isDesign ? "text-sm" : "text-2xl")}>AI</span>
      </div>
      <div className={cn("min-w-0", isCoding || isDesign ? "flex-1" : "w-full max-w-md")}>
        <Waveform
          active={voiceState === "speaking"}
          level={voiceState === "listening" ? level : undefined}
          bars={isCoding || isDesign ? 28 : 36}
          className={cn(isCoding || isDesign ? "h-8" : "h-14", voiceState === "listening" ? "text-success" : "text-primary")}
        />
        <p className="mt-1 text-xs text-studio-foreground/60" aria-live="polite">
          {thinking ? (
            <span className="inline-flex items-center gap-1.5">
              <Loader2 className="size-3 animate-spin" /> Thinking
            </span>
          ) : (
            STATE_LABEL[presence]
          )}
        </p>
      </div>
    </div>
  );

  const questionCard = live.question && (
    <div key={live.question.text} className="animate-fade-up rounded-2xl bg-white/5 p-5 ring-1 ring-white/10">
      <p className="text-[11px] tracking-wide text-studio-foreground/50 uppercase">
        {live.question.kind === "followup"
          ? `Follow-up${live.question.followup_type ? ` · ${live.question.followup_type.replace("_", " ")}` : ""}`
          : live.question.kind === "code_review"
            ? "Code review"
            : (currentRound?.title ?? "Question")}
      </p>
      <p className={cn("mt-2 leading-relaxed", isCoding ? "text-[15px]" : "text-lg sm:text-xl")}>{live.question.text}</p>
    </div>
  );

  const composer = (
    <div className="space-y-2">
      {!typeMode && (
        <div className="min-h-12 rounded-xl bg-white/5 px-4 py-3 text-sm ring-1 ring-white/10" aria-live="polite" aria-label="Your answer (live transcript)">
          {partial ? <span>{partial}</span> : <span className="text-studio-foreground/40">{waitingAnswer ? (muted ? "Microphone muted" : "Start speaking when you're ready…") : live.next_action === "WAIT_FOR_CODE" ? "Work in the editor and submit when ready." : "…"}</span>}
        </div>
      )}
      {typeMode && (
        <div className="flex gap-2">
          <Textarea
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submitTyped();
            }}
            placeholder={waitingAnswer ? "Type your answer… (Ctrl+Enter to send)" : "Waiting for the interviewer…"}
            disabled={!waitingAnswer}
            rows={isCoding || isDesign ? 2 : 3}
            aria-label="Type your answer"
            className="resize-none border-white/15 bg-white/5 text-studio-foreground placeholder:text-studio-foreground/40"
          />
          <Button onClick={submitTyped} disabled={!typed.trim() || !waitingAnswer} className="self-end" aria-label="Send answer">
            <Send className="size-4" />
          </Button>
        </div>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-studio-foreground/60">
        <button onClick={() => void switchMode()} className="inline-flex items-center gap-1 hover:text-studio-foreground">
          {typeMode ? <Mic className="size-3.5" /> : <Keyboard className="size-3.5" />} {typeMode ? "Answer by voice" : "Type instead"}
        </button>
        <div className="flex items-center gap-2">
          {!typeMode && partial && waitingAnswer && (
            <Button size="sm" variant="secondary" onClick={() => voice.current?.commitAnswer()}>
              <Square className="size-3" /> Done answering
            </Button>
          )}
          {waitingAnswer && (
            <button
              onClick={() => {
                send("ANSWER", { text: "I'd like to skip this question.", source: "typed" });
                setThinking(true);
              }}
              className="inline-flex items-center gap-1 hover:text-studio-foreground"
            >
              <SkipForward className="size-3.5" /> Skip
            </button>
          )}
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex h-screen flex-col bg-studio text-studio-foreground">
      {/* Header */}
      <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-white/10 px-4">
        <div className="flex min-w-0 items-center gap-3">
          <span className="size-2 shrink-0 rounded-full bg-success" aria-hidden />
          <span className="text-sm font-medium">AI Interviewer</span>
          <span className="hidden truncate text-sm text-studio-foreground/50 sm:inline">· {interview.plan.role_title}</span>
          <MockNotice show={live.ai_is_mock} className="hidden border-white/20 text-studio-foreground/50 md:inline-flex" />
        </div>
        <ol className="hidden items-center gap-1.5 lg:flex" aria-label="Rounds">
          {live.rounds.map((r) => (
            <li key={r.id} title={`${r.title} (${r.status})`} className={cn("h-1.5 w-8 rounded-full", r.status === "completed" ? "bg-success" : r.status === "active" ? "bg-primary" : "bg-white/15")}>
              <span className="sr-only">
                {r.title}: {r.status}
              </span>
            </li>
          ))}
        </ol>
        <div className="flex items-center gap-3 text-sm">
          <span className={cn("rounded-md px-2 py-1 font-mono tabular", remaining < 120 ? "bg-destructive/20 text-red-300" : "bg-white/10")} aria-label="Time remaining">
            {formatDuration(remaining)}
          </span>
          <span className={cn("hidden items-center gap-1 text-xs sm:inline-flex", conn === "connected" ? "text-studio-foreground/60" : "text-amber-300")} role="status">
            {conn === "connected" ? <Wifi className="size-3.5" /> : <WifiOff className="size-3.5" />}
            {conn === "connected" ? "Connected" : conn === "reconnecting" ? "Reconnecting…" : conn === "connecting" ? "Connecting…" : "Disconnected"}
          </span>
          <Button size="sm" variant="destructive" onClick={() => setConfirmEnd(true)} className="bg-destructive/90 text-white hover:bg-destructive">
            Exit
          </Button>
        </div>
      </header>

      {conn !== "connected" && (
        <div role="alert" className="bg-amber-500/15 px-4 py-1.5 text-center text-xs text-amber-200">
          Connection lost — reconnecting. Your progress is saved.
        </div>
      )}

      {/* Body */}
      {isCoding && live.coding?.problem ? (
        <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(320px,0.9fr)_1.4fr]">
          <div className="flex min-h-0 flex-col gap-4 overflow-y-auto border-r border-white/10 p-4">
            {presencePanel}
            {live.phase === "CODE_REVIEW" && questionCard}
            <div className="rounded-xl bg-background p-4 text-foreground">
              <ProblemPanel problem={live.coding.problem} isSql={live.coding.is_sql} />
            </div>
            {composer}
          </div>
          <div className="min-h-[60vh] bg-background text-foreground">
            <CodeWorkspace
              key={live.coding.problem.id}
              interviewId={id}
              starter={live.coding.problem.starter}
              initialCode={live.coding.code}
              initialLanguage={live.coding.language}
              isSql={live.coding.is_sql}
              submitted={live.coding.submitted}
              onCodeChange={(code) => send("CODE_CHANGED", { code })}
              onSubmitted={() => undefined}
            />
          </div>
        </div>
      ) : isDesign ? (
        <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[minmax(320px,0.8fr)_1.4fr]">
          <div className="flex min-h-0 flex-col gap-4 overflow-y-auto border-r border-white/10 p-4">
            {presencePanel}
            {questionCard}
            <TranscriptLines lines={lines} />
            {composer}
          </div>
          <div className="min-h-[60vh] bg-background text-foreground">
            <DesignCanvas interviewId={id} />
          </div>
        </div>
      ) : (
        <div className="mx-auto flex min-h-0 w-full max-w-3xl flex-1 flex-col gap-6 overflow-y-auto px-4 py-8">
          {presencePanel}
          {questionCard ?? (
            <p className="text-center text-studio-foreground/60" aria-live="polite">
              {caption || "The interviewer will begin shortly…"}
            </p>
          )}
          <div className="flex-1" />
          <TranscriptLines lines={lines} />
          {composer}
        </div>
      )}

      {/* Self view */}
      {cameraOn && (
        <video ref={camRef} autoPlay muted playsInline className="pointer-events-none fixed right-4 bottom-24 z-20 aspect-video w-44 rounded-lg object-cover ring-2 ring-white/20" />
      )}

      {/* Controls */}
      <footer className="flex shrink-0 items-center justify-center gap-3 border-t border-white/10 py-3">
        <ControlButton label={muted ? "Unmute microphone" : "Mute microphone"} onClick={toggleMute} active={!muted && !typeMode} disabled={typeMode}>
          {muted || typeMode ? <MicOff className="size-5" /> : <Mic className="size-5" />}
        </ControlButton>
        <ControlButton
          label={screen.state === "sharing" ? "Stop sharing screen" : interview.consent.screen_share ? "Share screen" : "Screen sharing not consented"}
          onClick={() => (screen.state === "sharing" ? screen.stop() : void screen.start())}
          active={screen.state === "sharing"}
          disabled={!interview.consent.screen_share || screen.state === "unsupported"}
        >
          {screen.state === "sharing" ? <MonitorOff className="size-5" /> : <MonitorUp className="size-5" />}
        </ControlButton>
        {screen.state === "sharing" && (
          <ControlButton label="Share a snapshot with the interviewer" onClick={() => void screen.snapshot("candidate_shared").then((ok) => ok && toast.success("Snapshot shared"))}>
            <Code2 className="size-5" />
          </ControlButton>
        )}
        <ControlButton label={cameraOn ? "Turn camera off" : "Turn camera on (self-view only)"} onClick={() => void toggleCamera()} active={cameraOn}>
          {cameraOn ? <Video className="size-5" /> : <VideoOff className="size-5" />}
        </ControlButton>
        <ControlButton
          label={bargeIn ? "Voice interrupt on (headphones)" : "Enable voice interrupt (use headphones)"}
          onClick={() => {
            setBargeIn(!bargeIn);
            voice.current?.setBargeIn(!bargeIn);
          }}
          active={bargeIn}
          disabled={typeMode}
        >
          <Headphones className="size-5" />
        </ControlButton>
        {isDesign && (
          <span className="hidden items-center gap-1 text-xs text-studio-foreground/60 md:inline-flex">
            <Network className="size-3.5" /> Design autosaves
          </span>
        )}
        <ControlButton label="End interview" onClick={() => setConfirmEnd(true)} danger>
          <PhoneOff className="size-5" />
        </ControlButton>
      </footer>
      {screen.state === "denied" && <p className="sr-only" role="status">Screen sharing permission required</p>}

      <AlertDialog open={confirmEnd} onOpenChange={setConfirmEnd}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>End the interview now?</AlertDialogTitle>
            <AlertDialogDescription>You&apos;ll get an evaluation based on the questions you&apos;ve answered so far. Unanswered rounds won&apos;t be scored.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Continue interview</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                voice.current?.stopSpeaking();
                send("END");
                setEnding(true);
              }}
            >
              End and evaluate
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function TranscriptLines({ lines }: { lines: Line[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight, behavior: "smooth" });
  }, [lines]);
  if (!lines.length) return null;
  return (
    <div ref={ref} className="max-h-48 space-y-2 overflow-y-auto rounded-xl bg-black/20 p-3 text-sm" aria-label="Captions">
      {lines.slice(-12).map((l) => (
        <p key={l.id} className={cn(l.speaker === "candidate" ? "text-studio-foreground" : "text-studio-foreground/60")}>
          <span className="mr-1.5 text-xs font-medium tracking-wide uppercase opacity-60">{l.speaker === "candidate" ? "You" : "AI"}</span>
          {l.text}
        </p>
      ))}
    </div>
  );
}
