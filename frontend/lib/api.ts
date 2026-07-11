// Thin client for the CallSense API.
//
// On the hosted site the browser uses the SAME-ORIGIN proxy (/api/backend →
// rewritten by Vercel's edge to the backend) so clients never resolve the
// backend host directly — some ISPs block *.up.railway.app DNS. Locally the
// env var (or localhost default) talks to the API directly.

function resolveApiBase(): string {
  if (typeof window !== "undefined" && window.location.hostname.endsWith(".vercel.app")) {
    return "/api/backend";
  }
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
}

export const API_BASE = resolveApiBase();

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) }),
};

export async function uploadCall(form: FormData): Promise<any> {
  const res = await fetch(`${API_BASE}/ingest/upload`, {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
