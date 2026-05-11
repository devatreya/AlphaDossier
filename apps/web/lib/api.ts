import type {
  AuditListResponse,
  CitationListResponse,
  ThesisCreateRequest,
  ThesisCreateResponse,
  ThesisGetResponse,
} from "./types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type ReadinessResponse = {
  status: "ok" | "degraded";
  env: string;
  db: "ok" | "unavailable";
  providers: Record<string, boolean>;
};

class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly body: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (res.status === 503 || res.status === 404) {
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      body = null;
    }
    throw new ApiError(
      `API ${res.status} ${path}`,
      res.status,
      body,
    );
  }
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = await res.json();
    } catch {
      detail = await res.text();
    }
    throw new ApiError(
      `API ${res.status} ${path}: ${JSON.stringify(detail)}`,
      res.status,
      detail,
    );
  }
  return (await res.json()) as T;
}

/** Hits /readyz; returns parsed body for both 200 (ok) and 503 (degraded). */
export async function getApiReadiness(): Promise<ReadinessResponse> {
  const res = await fetch(`${API_BASE_URL}/readyz`, { cache: "no-store" });
  if (res.status !== 200 && res.status !== 503) {
    throw new ApiError(
      `Readiness check failed: ${res.status}`,
      res.status,
      null,
    );
  }
  return (await res.json()) as ReadinessResponse;
}

/** Optional per-call options. `signal` lets callers abort an in-flight fetch
 * (used by the thesis page to cancel polls when the route changes). */
export type FetchOpts = { signal?: AbortSignal };

export async function createThesis(
  req: ThesisCreateRequest,
  opts: FetchOpts = {},
): Promise<ThesisCreateResponse> {
  return fetchJson<ThesisCreateResponse>("/thesis", {
    method: "POST",
    body: JSON.stringify(req),
    signal: opts.signal,
  });
}

export async function getThesis(
  thesisId: string,
  opts: FetchOpts = {},
): Promise<ThesisGetResponse> {
  return fetchJson<ThesisGetResponse>(`/thesis/${thesisId}`, {
    signal: opts.signal,
  });
}

export async function getCitations(
  thesisId: string,
  opts: FetchOpts = {},
): Promise<CitationListResponse> {
  return fetchJson<CitationListResponse>(`/thesis/${thesisId}/citations`, {
    signal: opts.signal,
  });
}

export async function getAudit(
  thesisId: string,
  limit: number = 200,
  opts: FetchOpts = {},
): Promise<AuditListResponse> {
  return fetchJson<AuditListResponse>(
    `/thesis/${thesisId}/audit?limit=${limit}`,
    { signal: opts.signal },
  );
}

/** True for fetch errors caused by an AbortController firing. */
export function isAbortError(e: unknown): boolean {
  return (
    e instanceof DOMException && e.name === "AbortError"
  ) || (e instanceof Error && e.name === "AbortError");
}

export { ApiError };
export const apiBaseUrl = API_BASE_URL;
