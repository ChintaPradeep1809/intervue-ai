"use client";

import type { VoiceSessionConfig, WsEvent } from "@intervue/types";
import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";

export type ConnectionStatus = "connecting" | "connected" | "reconnecting" | "disconnected";

interface Ticket {
  ticket: string;
  ws_url: string;
  voice: VoiceSessionConfig;
}

/** Interview WebSocket with ticket auth, heartbeat and automatic reconnection. */
export function useInterviewSocket(interviewId: string | undefined, onEvent: (e: WsEvent) => void) {
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const [voice, setVoice] = useState<VoiceSessionConfig | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const handler = useRef(onEvent);
  const closedByUs = useRef(false);
  const attempts = useRef(0);
  const queue = useRef<string[]>([]);

  useEffect(() => {
    handler.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    if (!interviewId) return;
    closedByUs.current = false;
    let cancelled = false; // per-effect flag: an await may resolve after cleanup (e.g. StrictMode remount)
    let ping: ReturnType<typeof setInterval> | undefined;
    let retry: ReturnType<typeof setTimeout> | undefined;

    const connect = async () => {
      let t: Ticket;
      try {
        t = await api<Ticket>(`/interviews/${interviewId}/ws-ticket`, { method: "POST" });
      } catch {
        scheduleRetry();
        return;
      }
      if (cancelled) return;
      setVoice(t.voice);
      const ws = new WebSocket(`${t.ws_url}?ticket=${encodeURIComponent(t.ticket)}`);
      wsRef.current = ws;
      ws.onopen = () => {
        attempts.current = 0;
        setStatus("connected");
        for (const m of queue.current.splice(0)) ws.send(m);
        ping = setInterval(() => ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify({ type: "PING" })), 20000);
      };
      ws.onmessage = (m) => {
        try {
          handler.current(JSON.parse(m.data as string) as WsEvent);
        } catch {
          /* ignore malformed frames */
        }
      };
      ws.onclose = () => {
        if (ping) clearInterval(ping);
        if (!cancelled) scheduleRetry();
      };
    };

    const scheduleRetry = () => {
      if (cancelled) return;
      attempts.current += 1;
      setStatus(attempts.current > 6 ? "disconnected" : "reconnecting");
      const delay = Math.min(10000, 500 * 2 ** Math.min(attempts.current, 5));
      retry = setTimeout(connect, delay);
    };

    void connect();
    const online = () => {
      if (wsRef.current?.readyState !== WebSocket.OPEN) {
        attempts.current = 0;
        void connect();
      }
    };
    window.addEventListener("online", online);
    return () => {
      cancelled = true;
      closedByUs.current = true;
      window.removeEventListener("online", online);
      if (ping) clearInterval(ping);
      if (retry) clearTimeout(retry);
      wsRef.current?.close();
    };
  }, [interviewId]);

  const send = useCallback((type: string, payload: Record<string, unknown> = {}) => {
    const msg = JSON.stringify({ type, ...payload });
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(msg);
    else if (type !== "PING" && type !== "TRANSCRIPT_PARTIAL") queue.current.push(msg);
  }, []);

  return { status, send, voice };
}
