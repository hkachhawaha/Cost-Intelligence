// Typed fetch client for the FastAPI backend.
// Attaches the Auth0 access token as a Bearer header (resolved lazily so this
// module is importable in plain test environments), normalizes errors, parses JSON.

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
    public requestId?: string,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

/** Server-side typed fetch. */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { DEV_AUTH } = await import("@/lib/dev");
  // Local dev: backend's dev_auth_bypass injects the demo principal — send no Auth0 token.
  const authHeader: Record<string, string> = {};
  if (!DEV_AUTH) {
    const { getAccessToken } = await import("@auth0/nextjs-auth0");
    const { accessToken } = await getAccessToken();
    authHeader.Authorization = `Bearer ${accessToken}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...authHeader,
      ...init.headers,
    },
    cache: "no-store",
  });

  const requestId = res.headers.get("x-request-id") ?? undefined;
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail, requestId);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string) => apiFetch<T>(path),
  post: <T>(path: string, body: unknown) =>
    apiFetch<T>(path, { method: "POST", body: JSON.stringify(body) }),
};

// ── Phase 5 ─────────────────────────────────────────────────────────────────
// Server components read through `apiServer` (Auth0 token injected server-side,
// always fresh — memory is the cache). Client components mutate through
// `apiClient` (cookie-credentialed; token attached by the browser session).

export const apiServer = {
  get: <T>(path: string) => apiFetch<T>(path),
};

async function clientFetch<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: "include",
    cache: "no-store",
  });
  const requestId = res.headers.get("x-request-id") ?? undefined;
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail, requestId);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const apiClient = {
  get: <T>(path: string) => clientFetch<T>("GET", path),
  post: <T>(path: string, body: unknown) => clientFetch<T>("POST", path, body),
  patch: <T>(path: string, body: unknown) => clientFetch<T>("PATCH", path, body),
};
