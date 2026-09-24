/**
 * API client. The admin token lives ONLY in memory (a module variable set from the login screen): never in
 * localStorage, sessionStorage, cookies or a URL. A page reload means signing in again — by design.
 */
export type ApiError = { status: number; error_code: string; message: string; request_id?: string; fields?: string[] };

let adminToken: string | null = null;
const listeners = new Set<(signedIn: boolean) => void>();

export function setAdminToken(token: string | null) {
  adminToken = token;
  listeners.forEach((l) => l(token !== null));
}
export function isSignedIn() {
  return adminToken !== null;
}
export function onAuthChange(fn: (signedIn: boolean) => void) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

async function request<T>(method: string, path: string, body?: unknown, admin = false): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (admin && adminToken) headers.Authorization = `Bearer ${adminToken}`;
  const res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const err: ApiError = { status: res.status, error_code: data?.error_code ?? "http_error", message: data?.message ?? res.statusText,
      request_id: data?.request_id, fields: data?.fields };
    if (res.status === 401 && admin) setAdminToken(null);
    throw err;
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body: unknown) => request<T>("POST", path, body),
  admin: {
    get: <T>(path: string) => request<T>("GET", path, undefined, true),
    post: <T>(path: string, body: unknown = {}) => request<T>("POST", path, body, true),
    put: <T>(path: string, body: unknown) => request<T>("PUT", path, body, true),
  },
};

export async function signIn(token: string): Promise<boolean> {
  const prev = adminToken;
  adminToken = token;
  try {
    await request("GET", "/v1/session", undefined, true);
    setAdminToken(token);
    return true;
  } catch {
    adminToken = prev;
    return false;
  }
}

/** A traveller's search session id: not a secret, shared across tabs so "same search, same price" can be shown. */
export function sessionId(): string {
  const key = "rl.session";
  try {
    const existing = localStorage.getItem(key);
    if (existing && /^[A-Za-z0-9_-]{8,64}$/.test(existing)) return existing;
    const bytes = crypto.getRandomValues(new Uint8Array(12));
    const id = "sess_" + Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    localStorage.setItem(key, id);
    return id;
  } catch {
    return "sess_ephemeral_" + Math.random().toString(16).slice(2, 14);
  }
}
