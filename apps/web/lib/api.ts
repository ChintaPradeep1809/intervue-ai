export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

const FRIENDLY: Record<number, string> = {
  0: "Network connection lost. Check your internet and try again.",
  401: "Your session has expired. Please sign in again.",
  403: "You don't have access to this.",
  404: "We couldn't find that.",
  409: "That action isn't possible right now.",
  413: "That file is too large.",
  429: "Too many requests. Please wait a moment and try again.",
  500: "Something went wrong on our side. Please try again.",
  503: "This service is temporarily unavailable. Please try again shortly.",
};

type Body = Record<string, unknown> | unknown[] | FormData | undefined;

export async function api<T>(
  path: string,
  init: { method?: string; body?: Body; signal?: AbortSignal } = {},
): Promise<T> {
  const { method = init.body ? "POST" : "GET", body, signal } = init;
  const headers: Record<string, string> = { Accept: "application/json" };
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { method, body: payload, headers, credentials: "include", signal });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(0, FRIENDLY[0]);
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let data: unknown = undefined;
  try {
    data = text ? JSON.parse(text) : undefined;
  } catch {
    data = undefined;
  }
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | undefined)?.detail;
    const msg = typeof detail === "string" ? detail : (FRIENDLY[res.status] ?? FRIENDLY[500]);
    throw new ApiError(res.status, msg);
  }
  return data as T;
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error && e.message) return e.message;
  return "Something went wrong.";
}
