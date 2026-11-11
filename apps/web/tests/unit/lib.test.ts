import { afterEach, describe, expect, it, vi } from "vitest";

import { api, ApiError, errorMessage } from "@/lib/api";
import { formatDuration, scoreTone, titleCase } from "@/lib/format";
import { homeFor } from "@/lib/session";
import { pickSpeechVoice } from "@/lib/voice/browser";

afterEach(() => vi.unstubAllGlobals());

describe("api client", () => {
  it("returns parsed JSON and sends JSON bodies with credentials", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: 1 }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(api<{ ok: number }>("/thing", { body: { a: 1 } })).resolves.toEqual({ ok: 1 });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/thing");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("include");
    expect(init.headers["Content-Type"]).toBe("application/json");
  });

  it("surfaces the server's friendly detail message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Monthly interview limit reached (3)." }), { status: 402 })));
    const err = await api("/interviews", { body: {} }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).status).toBe(402);
    expect(errorMessage(err)).toBe("Monthly interview limit reached (3).");
  });

  it("never shows raw stack traces for 500s or network failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("Traceback (most recent call last): ...", { status: 500 })));
    expect(errorMessage(await api("/x").catch((e) => e))).toBe("Something went wrong on our side. Please try again.");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    expect(errorMessage(await api("/x").catch((e) => e))).toMatch(/Network connection lost/);
  });

  it("does not set a JSON content type for file uploads", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);
    const fd = new FormData();
    fd.append("file", new Blob(["x"]), "cv.pdf");
    await api("/documents/resume", { body: fd });
    expect(fetchMock.mock.calls[0][1].headers["Content-Type"]).toBeUndefined();
  });
});

describe("formatting", () => {
  it("formats timers and tones", () => {
    expect(formatDuration(125)).toBe("02:05");
    expect(formatDuration(-4)).toBe("00:00");
    expect(scoreTone(82)).toBe("success");
    expect(scoreTone(60)).toBe("warning");
    expect(scoreTone(30)).toBe("destructive");
    expect(scoreTone(null)).toBe("muted");
    expect(titleCase("system_design")).toBe("System Design");
  });
});

describe("routing by role", () => {
  const base = { id: "1", email: "a@b.co", full_name: "A", is_demo: false, organizations: [], onboarding_completed: true };
  it("sends each role to its home", () => {
    expect(homeFor(null)).toBe("/auth/login");
    expect(homeFor({ ...base, role: "super_admin" })).toBe("/admin");
    expect(homeFor({ ...base, role: "candidate" })).toBe("/dashboard");
    expect(homeFor({ ...base, role: "candidate", onboarding_completed: false })).toBe("/onboarding");
    expect(homeFor({ ...base, role: "organization_admin", organizations: [{ id: "o", name: "O", role: "admin", kind: "college" }] })).toBe("/organization");
  });
});

describe("pickSpeechVoice", () => {
  const v = (name: string, lang: string, localService: boolean) => ({ name, lang, localService }) as SpeechSynthesisVoice;
  const voices = [
    v("Google US English", "en-US", false),
    v("Microsoft Heera - English (India)", "en-IN", true),
    v("Microsoft Zira - English (United States)", "en-US", true),
  ];

  it("prefers the session language", () => {
    expect(pickSpeechVoice(voices, "en-IN", false)?.name).toMatch(/Heera/);
  });

  it("skips network voices when offline", () => {
    expect(pickSpeechVoice(voices, "en-US", false)?.name).toBe("Google US English");
    expect(pickSpeechVoice(voices, "en-US", true)?.name).toMatch(/Zira/);
  });
});
