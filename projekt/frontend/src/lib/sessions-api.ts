import type {
  CrawlSession,
  SessionInput,
  SessionList,
  SessionStatus,
} from "@/types/sessions";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public fields: string[] = [],
  ) {
    super(message);
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const base = (
    import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"
  ).replace(/\/$/, "");
  const timeout = AbortSignal.timeout(5000);
  let response: Response;
  try {
    response = await fetch(`${base}${path}`, {
      ...options,
      signal: options.signal
        ? AbortSignal.any([options.signal, timeout])
        : timeout,
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
    });
  } catch (error) {
    if (options.signal?.aborted) throw error;
    throw new ApiError(0, "Brak połączenia z backendem. Spróbuj ponownie.");
  }
  if (!response.ok) {
    let data: unknown;
    try {
      data = await response.json();
    } catch {
      /* Non-JSON HTTP errors use a Polish fallback. */
    }
    const payload = data as
      | { message?: unknown; details?: { location?: unknown }[] }
      | undefined;
    const fields = Array.isArray(payload?.details)
      ? payload.details.flatMap((detail) =>
          Array.isArray(detail?.location)
            ? [detail.location.filter((part) => part !== "body").join(".")]
            : [],
        )
      : [];
    throw new ApiError(
      response.status,
      typeof payload?.message === "string"
        ? payload.message
        : "Nie udało się wykonać operacji.",
      fields,
    );
  }
  if (response.status === 204) return undefined as T;
  try {
    return (await response.json()) as T;
  } catch {
    throw new ApiError(response.status, "Nieprawidłowa odpowiedź serwera.");
  }
}

export function eventsUrl(id: string): string {
  const base = (
    import.meta.env.VITE_API_BASE_URL || "http://localhost:8000"
  ).replace(/\/$/, "");
  return `${base}/api/sessions/${encodeURIComponent(id)}/events`;
}

export const sessionsApi = {
  start: (id: string) =>
    request<CrawlSession>(`/api/sessions/${encodeURIComponent(id)}/start`, {
      method: "POST",
    }),
  cancel: (id: string) =>
    request<CrawlSession>(`/api/sessions/${encodeURIComponent(id)}/cancel`, {
      method: "POST",
    }),
  list: (offset = 0, status: SessionStatus | "" = "", signal?: AbortSignal) =>
    request<SessionList>(
      `/api/sessions?offset=${offset}&limit=10${status ? `&status=${status}` : ""}`,
      { signal },
    ),
  read: (id: string, signal?: AbortSignal) =>
    request<CrawlSession>(`/api/sessions/${encodeURIComponent(id)}`, {
      signal,
    }),
  create: (input: SessionInput) =>
    request<CrawlSession>("/api/sessions", {
      method: "POST",
      body: JSON.stringify(input),
    }),
  update: (id: string, input: SessionInput) =>
    request<CrawlSession>(`/api/sessions/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(input),
    }),
  remove: (id: string) =>
    request<void>(`/api/sessions/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),
};
