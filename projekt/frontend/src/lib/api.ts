export interface HealthResponse {
  status: "ok" | "error"
  database: "ok" | "unavailable"
}

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const base = (import.meta.env.VITE_API_BASE_URL || "http://localhost:8000").replace(/\/$/, "")
  const response = await fetch(`${base}/health`, {
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(5000)]) : AbortSignal.timeout(5000),
  })
  const data: unknown = await response.json()
  if (typeof data === "object" && data !== null && "status" in data && "database" in data) {
    if (response.status === 200 && data.status === "ok" && data.database === "ok") {
      return { status: "ok", database: "ok" }
    }
    if (response.status === 503 && data.status === "error" && data.database === "unavailable") {
      return { status: "error", database: "unavailable" }
    }
  }
  throw new Error("Nieprawidłowa odpowiedź serwera")
}
