"use client";

import type { InterviewDetail } from "@intervue/types";
import { CheckCircle2, Circle, Globe2, Headphones, Mic, MonitorUp, Video, Wifi, XCircle } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Waveform } from "@/components/interview/waveform";
import { ErrorState, LoadingBlock, PageHeader, Spinner } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { api, errorMessage } from "@/lib/api";
import { pickSpeechVoice } from "@/lib/voice";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";

type CheckState = "idle" | "running" | "ok" | "fail";

function CheckRow({
  icon: Icon,
  title,
  state,
  detail,
  action,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  state: CheckState;
  detail: string;
  action?: React.ReactNode;
  children?: React.ReactNode;
}) {
  const StateIcon = state === "ok" ? CheckCircle2 : state === "fail" ? XCircle : state === "running" ? Spinner : Circle;
  return (
    <li className="rounded-xl border bg-card p-4">
      <div className="flex items-center gap-3">
        <Icon className="size-5 shrink-0 text-muted-foreground" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium">{title}</p>
          <p className="text-xs text-muted-foreground">{detail}</p>
        </div>
        {action}
        <StateIcon className={cn("size-5 shrink-0", state === "ok" ? "text-success" : state === "fail" ? "text-destructive" : "text-muted-foreground")} aria-label={state} />
      </div>
      {children}
    </li>
  );
}

export default function SetupPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { data: iv, error, loading, reload } = useApi<InterviewDetail>(`/interviews/${id}`);

  const [voiceSupported, setVoiceSupported] = useState<boolean | null>(null);
  const [mic, setMic] = useState<CheckState>("idle");
  const [level, setLevel] = useState(0);
  const [speaker, setSpeaker] = useState<CheckState>("idle");
  const [camera, setCamera] = useState<CheckState>("idle");
  const [net, setNet] = useState<{ state: CheckState; ms?: number }>({ state: "running" });
  const [consent, setConsent] = useState({ ai_processing: false, data_retention_ack: false, microphone: true, screen_share: false, camera: false });
  const [busy, setBusy] = useState(false);
  const micStream = useRef<MediaStream | null>(null);
  const camStream = useRef<MediaStream | null>(null);
  const camVideo = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const w = window as unknown as Record<string, unknown>;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- feature detection runs once on mount
    setVoiceSupported(!!(w.SpeechRecognition || w.webkitSpeechRecognition));
    const t0 = performance.now();
    api("/health")
      .then(() => setNet({ state: "ok", ms: Math.round(performance.now() - t0) }))
      .catch(() => setNet({ state: "fail" }));
    return () => {
      micStream.current?.getTracks().forEach((t) => t.stop());
      camStream.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  useEffect(() => {
    if (iv?.status === "in_progress") router.replace(`/interviews/${id}/room`);
    if (iv?.status === "completed" || iv?.status === "evaluating") router.replace(`/interviews/${id}/report`);
  }, [iv, id, router]);

  async function testMic() {
    setMic("running");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      micStream.current = stream;
      const ctx = new AudioContext();
      const an = ctx.createAnalyser();
      ctx.createMediaStreamSource(stream).connect(an);
      const buf = new Uint8Array(an.fftSize);
      let heard = false;
      const start = performance.now();
      const tick = () => {
        an.getByteTimeDomainData(buf);
        let s = 0;
        for (const v of buf) s += ((v - 128) / 128) ** 2;
        const l = Math.min(1, Math.sqrt(s / buf.length) * 4);
        setLevel(l);
        if (l > 0.12) heard = true;
        if (performance.now() - start < 6000) requestAnimationFrame(tick);
        else {
          setMic(heard ? "ok" : "fail");
          setLevel(0);
          stream.getTracks().forEach((t) => t.stop());
          void ctx.close();
        }
      };
      tick();
    } catch {
      setMic("fail");
      setConsent((c) => ({ ...c, microphone: false }));
      toast.error("Microphone permission was denied. You can still type your answers.");
    }
  }

  function speakOnDevice(text: string, lang: string) {
    if (!("speechSynthesis" in window)) {
      setSpeaker("fail");
      toast.error("This browser can't play speech. Questions will still be shown on screen.");
      return;
    }
    const u = new SpeechSynthesisUtterance(text);
    const voice = pickSpeechVoice(window.speechSynthesis.getVoices(), lang, !navigator.onLine);
    if (voice) u.voice = voice;
    u.onend = () => setSpeaker("ok");
    u.onerror = () => setSpeaker("fail");
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
  }

  /** Plays the interviewer's real voice (server TTS when configured), so the check matches the interview. */
  async function testSpeaker() {
    setSpeaker("running");
    // created inside the click so the browser allows playback after the fetch
    const el = new Audio();
    let preview: { text: string; language: string; audio: { mime_type: string; b64: string } | null; error?: string };
    try {
      preview = await api("/voice/preview");
    } catch {
      speakOnDevice("Hi, this is your interviewer. If you can hear me clearly, you're all set.", "en-US");
      return;
    }
    if (!preview.audio) {
      if (preview.error) toast.message("The interviewer's voice service is unavailable right now; using on-device speech.");
      speakOnDevice(preview.text, preview.language);
      return;
    }
    el.src = `data:${preview.audio.mime_type};base64,${preview.audio.b64}`;
    el.onended = () => setSpeaker("ok");
    el.onerror = () => speakOnDevice(preview.text, preview.language);
    el.play().catch(() => speakOnDevice(preview.text, preview.language));
  }

  async function toggleCamera() {
    if (camStream.current) {
      camStream.current.getTracks().forEach((t) => t.stop());
      camStream.current = null;
      setCamera("idle");
      setConsent((c) => ({ ...c, camera: false }));
      return;
    }
    try {
      const s = await navigator.mediaDevices.getUserMedia({ video: true });
      camStream.current = s;
      if (camVideo.current) camVideo.current.srcObject = s;
      setCamera("ok");
      setConsent((c) => ({ ...c, camera: true }));
    } catch {
      setCamera("fail");
    }
  }

  async function enter() {
    setBusy(true);
    try {
      await api(`/interviews/${id}/consent`, { body: { ...consent, microphone: consent.microphone && mic !== "fail" } });
      sessionStorage.setItem(`iv-prefs-${id}`, JSON.stringify({ voice: consent.microphone && voiceSupported && mic !== "fail", camera: consent.camera }));
      camStream.current?.getTracks().forEach((t) => t.stop());
      router.push(`/interviews/${id}/room`);
    } catch (e) {
      toast.error(errorMessage(e));
      setBusy(false);
    }
  }

  if (loading) return <LoadingBlock rows={4} />;
  if (error || !iv) return <ErrorState message={error?.message ?? "Interview not found."} onRetry={reload} />;
  const canEnter = consent.ai_processing && consent.data_retention_ack;

  return (
    <>
      <PageHeader eyebrow="Before you begin" title={iv.title} description={`${iv.plan.duration_minutes} minutes · ${iv.plan.rounds.length} rounds · ${iv.plan.difficulty}`} />
      <div className="grid gap-8 lg:grid-cols-[1.1fr_1fr]">
        <section aria-labelledby="sys-h">
          <h2 id="sys-h" className="mb-3 text-sm font-medium">System check</h2>
          <ul className="space-y-3">
            <CheckRow
              icon={Globe2}
              title="Browser voice support"
              state={voiceSupported === null ? "running" : voiceSupported ? "ok" : "fail"}
              detail={voiceSupported === false ? "Voice answers need Chrome or Edge. You can type answers instead." : "Speech recognition is available."}
            />
            <CheckRow
              icon={Mic}
              title="Microphone"
              state={mic}
              detail={mic === "running" ? "Say a few words…" : mic === "ok" ? "We can hear you." : mic === "fail" ? "No sound detected or permission denied." : "Check that we can hear you."}
              action={
                <Button size="sm" variant="outline" onClick={testMic} disabled={mic === "running"}>
                  Test
                </Button>
              }
            >
              {mic === "running" && <Waveform active={false} level={level} className="mt-3 h-8 text-primary" bars={40} />}
            </CheckRow>
            <CheckRow
              icon={Headphones}
              title="Speakers"
              state={speaker}
              detail="The interviewer speaks each question aloud. Headphones work best."
              action={
                <Button size="sm" variant="outline" onClick={() => void testSpeaker()} disabled={speaker === "running"}>
                  Play
                </Button>
              }
            />
            <CheckRow
              icon={Video}
              title="Camera (optional)"
              state={camera}
              detail="Self-view only — video is never recorded or uploaded."
              action={
                <Button size="sm" variant="outline" onClick={toggleCamera}>
                  {camera === "ok" ? "Turn off" : "Preview"}
                </Button>
              }
            >
              <video ref={camVideo} autoPlay muted playsInline className={cn("mt-3 aspect-video w-full rounded-lg bg-muted object-cover", camera !== "ok" && "hidden")} />
            </CheckRow>
            <CheckRow icon={Wifi} title="Connection" state={net.state} detail={net.state === "ok" ? `Connected · ${net.ms} ms` : net.state === "fail" ? "Can't reach the server." : "Checking…"} />
          </ul>
        </section>

        <section aria-labelledby="consent-h" className="space-y-4">
          <h2 id="consent-h" className="text-sm font-medium">Consent</h2>
          <div className="space-y-4 rounded-xl border bg-card p-5 text-sm">
            {[
              { key: "ai_processing", required: true, label: "AI processing", body: "My answers are transcribed to text and processed by AI to run and evaluate this interview." },
              { key: "data_retention_ack", required: true, label: "Data storage", body: "The transcript, my code and scores are stored so I can review my report. I can delete them at any time. Audio and video are not recorded." },
              { key: "microphone", required: false, label: "Use my microphone", body: "Answer by voice. Uncheck to type your answers instead." },
              { key: "screen_share", required: false, label: "Allow screen sharing", body: "If I choose to share my screen, compressed snapshots may be taken during coding so the interviewer can see my work. I can stop sharing at any time." },
            ].map((c) => (
              <label key={c.key} className="flex cursor-pointer gap-3">
                <Checkbox
                  checked={consent[c.key as keyof typeof consent]}
                  onCheckedChange={(v) => setConsent((s) => ({ ...s, [c.key]: !!v }))}
                  className="mt-0.5"
                  aria-describedby={`${c.key}-d`}
                />
                <span>
                  <span className="font-medium">
                    {c.label}
                    {c.required && <span className="text-destructive"> *</span>}
                  </span>
                  <span id={`${c.key}-d`} className="mt-0.5 block text-muted-foreground">
                    {c.body}
                  </span>
                </span>
              </label>
            ))}
          </div>
          <div className="rounded-xl bg-muted/50 p-4 text-sm text-muted-foreground">
            <p className="flex items-center gap-2 font-medium text-foreground">
              <MonitorUp className="size-4" /> What to expect
            </p>
            <p className="mt-1">
              The interviewer greets you, explains the format and asks one question at a time. Speak naturally — it waits until you pause. You can
              ask it to repeat a question, type instead of speaking, or end the interview at any time.
            </p>
          </div>
          <Button className="h-11 w-full text-[15px]" disabled={!canEnter || busy} onClick={enter}>
            {busy && <Spinner />} Enter interview room
          </Button>
          {!canEnter && <p className="text-center text-xs text-muted-foreground">Accept the required items to continue.</p>}
        </section>
      </div>
    </>
  );
}
