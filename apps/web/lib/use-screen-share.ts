"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { api, errorMessage } from "@/lib/api";

export type ShareState = "idle" | "sharing" | "denied" | "unsupported" | "error";

const MAX_EDGE = 1280;

/**
 * Consent-first screen sharing. The display stream stays in the browser; only compressed JPEG
 * snapshots are uploaded, and only when the candidate shares one or the interviewer asks while
 * sharing is active.
 */
export function useScreenShare(interviewId: string | undefined) {
  const [state, setState] = useState<ShareState>(() =>
    typeof navigator !== "undefined" && !navigator.mediaDevices?.getDisplayMedia ? "unsupported" : "idle",
  );
  const [lastSnapshot, setLastSnapshot] = useState<{ at: Date; width: number; height: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  const post = useCallback(
    async (event_type: string, reason = "", image?: Blob) => {
      if (!interviewId) return null;
      const fd = new FormData();
      fd.append("event_type", event_type);
      if (reason) fd.append("reason", reason);
      if (image) fd.append("image", image, "snapshot.jpg");
      return api<{ width?: number; height?: number }>(`/interviews/${interviewId}/screen-events`, { method: "POST", body: fd });
    },
    [interviewId],
  );

  const stop = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setState((s) => {
      if (s === "sharing") void post("stopped").catch(() => undefined);
      return "idle";
    });
  }, [post]);

  const start = useCallback(async () => {
    if (!navigator.mediaDevices?.getDisplayMedia) {
      setState("unsupported");
      return false;
    }
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: 5 }, audio: false });
      streamRef.current = stream;
      const video = document.createElement("video");
      video.muted = true;
      video.playsInline = true;
      video.srcObject = stream;
      videoRef.current = video;
      await video.play().catch(() => undefined);
      stream.getVideoTracks()[0]?.addEventListener("ended", () => stop());
      setState("sharing");
      setError(null);
      await post("started").catch((e) => setError(errorMessage(e)));
      return true;
    } catch (e) {
      const name = (e as DOMException).name;
      setState(name === "NotAllowedError" ? "denied" : "error");
      if (name === "NotAllowedError") void post("denied").catch(() => undefined);
      return false;
    }
  }, [post, stop]);

  const snapshot = useCallback(
    async (reason: string) => {
      const video = videoRef.current;
      if (state !== "sharing" || !video || !video.videoWidth) return false;
      const scale = Math.min(1, MAX_EDGE / Math.max(video.videoWidth, video.videoHeight));
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(video.videoWidth * scale);
      canvas.height = Math.round(video.videoHeight * scale);
      canvas.getContext("2d")?.drawImage(video, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise<Blob | null>((r) => canvas.toBlob(r, "image/jpeg", 0.7));
      if (!blob) return false;
      try {
        const res = await post("snapshot", reason, blob);
        setLastSnapshot({ at: new Date(), width: res?.width ?? canvas.width, height: res?.height ?? canvas.height });
        return true;
      } catch (e) {
        setError(errorMessage(e));
        return false;
      }
    },
    [post, state],
  );

  useEffect(() => () => streamRef.current?.getTracks().forEach((t) => t.stop()), []);

  return { state, start, stop, snapshot, lastSnapshot, error, videoRef };
}
