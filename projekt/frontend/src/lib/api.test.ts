import { describe, expect, it, vi } from "vitest"
import { fetchHealth } from "./api"

describe("health client", () => {
  it("rejects unexpected HTTP status even with healthy body", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "ok", database: "ok" }), { status: 500 })))
    await expect(fetchHealth()).rejects.toThrow("Nieprawidłowa odpowiedź serwera")
  })
  it("sets finite timeout on request", async () => {
    const timeout = vi.spyOn(AbortSignal, "timeout")
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new DOMException("Timed out", "TimeoutError")))
    await expect(fetchHealth()).rejects.toThrow("Timed out")
    expect(timeout).toHaveBeenCalledWith(5000)
  })
  it("rejects invalid JSON", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("invalid")))
    await expect(fetchHealth()).rejects.toThrow()
  })
})
