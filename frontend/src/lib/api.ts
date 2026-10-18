export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const BASE = `${API_URL}/api/v1`;

const USER_KEY = "calibr.userId"; // UI preference only (demo user switcher)

export function getUserId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(USER_KEY);
}

export function setUserId(id: string) {
  window.localStorage.setItem(USER_KEY, id);
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
  }
}

function headers(extra?: HeadersInit): Headers {
  const h = new Headers(extra);
  const uid = getUserId();
  if (uid) h.set("X-User-Id", uid);
  return h;
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, ...rest } = init;
  const h = headers(rest.headers);
  let body = rest.body;
  if (json !== undefined) {
    h.set("Content-Type", "application/json");
    body = JSON.stringify(json);
  }
  const res = await fetch(`${BASE}${path}`, { ...rest, headers: h, body });
  if (!res.ok) {
    let code = "http_error";
    let message = `${res.status} ${res.statusText}`;
    let details: unknown;
    try {
      const data = (await res.json()) as { error?: { code: string; message: string; details?: unknown } };
      if (data.error) ({ code, message, details } = data.error);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, code, message, details);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function downloadUrl(path: string): string {
  return `${BASE}${path}`;
}

export interface SSEHandlers {
  onEvent: (event: string, data: unknown) => void;
  signal?: AbortSignal;
}

/** POST that returns text/event-stream; parses events incrementally. */
export async function postSSE(path: string, json: unknown, { onEvent, signal }: SSEHandlers) {
  const h = headers({ "Content-Type": "application/json" });
  const res = await fetch(`${BASE}${path}`, { method: "POST", headers: h, body: JSON.stringify(json), signal });
  if (!res.ok || !res.body) throw new ApiError(res.status, "stream_error", "Agent request failed");
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const raw = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      let event = "message";
      let data = "";
      for (const line of raw.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      onEvent(event, data ? JSON.parse(data) : null);
    }
  }
}
