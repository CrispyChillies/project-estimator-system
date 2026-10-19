// The API is served from the same site (Next.js rewrites /api/* to the backend), so the HTTP-only session cookie
// and the CSRF cookie are first-party.
const BASE = "/api/v1";

function csrfToken(): string {
  if (typeof document === "undefined") return "";
  const m = document.cookie.match(/(?:^|; )calibr_csrf=([^;]*)/);
  return m ? decodeURIComponent(m[1]) : "";
}

let csrfPromise: Promise<void> | null = null;
export async function ensureCsrf(): Promise<void> {
  if (csrfToken()) return;
  csrfPromise ??= fetch(`${BASE}/auth/csrf`, { credentials: "same-origin" }).then(() => undefined);
  await csrfPromise;
  csrfPromise = null;
}

const PUBLIC_PATHS = ["/", "/signin", "/signup", "/reset", "/help"];
function onUnauthorized() {
  if (typeof window === "undefined") return;
  const path = window.location.pathname;
  if (PUBLIC_PATHS.some((p) => path === p || (p !== "/" && path.startsWith(p)))) return;
  // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- full reload drops cached private data
  window.location.href = `/signin?next=${encodeURIComponent(path + window.location.search)}`;
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

function headers(extra?: HeadersInit, method = "GET"): Headers {
  const h = new Headers(extra);
  if (method !== "GET" && method !== "HEAD") h.set("X-CSRF-Token", csrfToken());
  return h;
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, ...rest } = init;
  const method = (rest.method ?? "GET").toUpperCase();
  if (method !== "GET") await ensureCsrf();
  const h = headers(rest.headers, method);
  let body = rest.body;
  if (json !== undefined) {
    h.set("Content-Type", "application/json");
    body = JSON.stringify(json);
  }
  const res = await fetch(`${BASE}${path}`, { ...rest, headers: h, body, credentials: "same-origin" });
  if (res.status === 401 && !path.startsWith("/auth/")) onUnauthorized();
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
  await ensureCsrf();
  const h = headers({ "Content-Type": "application/json", Accept: "text/event-stream" }, "POST");
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: h,
    body: JSON.stringify(json),
    signal,
    credentials: "same-origin",
  });
  if (res.status === 401) onUnauthorized();
  if (!res.ok || !res.body) {
    let code = "stream_error";
    let message = "Agent request failed";
    try {
      const data = (await res.json()) as { error?: { code: string; message: string } };
      if (data.error) ({ code, message } = data.error);
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, code, message);
  }
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
