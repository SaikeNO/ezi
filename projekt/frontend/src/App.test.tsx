import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it, vi } from "vitest"
import App from "./App"

function mount() { return render(<MemoryRouter><App /></MemoryRouter>) }
function health(status = 200, data: unknown = { status: "ok", database: "ok" }) {
  return new Response(JSON.stringify(data), { status })
}

describe("bootstrap UI", () => {
  it("shows loading then actual backend and SQLite health", async () => {
    let resolve!: (response: Response) => void
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(done => { resolve = done })))
    mount()
    expect(screen.getByRole("status")).toHaveTextContent("Sprawdzanie połączenia")
    expect(screen.getByRole("button", { name: /Sprawdź ponownie/ })).toBeDisabled()
    resolve(health())
    expect(await screen.findByText("Backend działa")).toBeInTheDocument()
    expect(screen.getByText("SQLite: połączenie aktywne")).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledWith("http://localhost:8000/health", expect.any(Object))
  })

  it("reports network failure and supports retry", async () => {
    const fetchMock = vi.fn().mockRejectedValueOnce(new TypeError("offline")).mockResolvedValueOnce(health())
    vi.stubGlobal("fetch", fetchMock)
    mount()
    expect(await screen.findByText("Brak połączenia z backendem")).toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: /Sprawdź ponownie/ }))
    expect(await screen.findByText("Backend działa")).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it("reports database failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(health(503, { status: "error", database: "unavailable" })))
    mount()
    expect(await screen.findByText("Backend odpowiada — baza danych niedostępna")).toBeInTheDocument()
  })

  it.each([{}, { status: "ok", database: "unavailable" }])("rejects malformed health: %j", async data => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(health(200, data)))
    mount()
    expect(await screen.findByText("Brak połączenia z backendem")).toBeInTheDocument()
  })

  it("navigation identifies deferred functionality, without fake metrics", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(url.endsWith("/health")
      ? health() : new Response(JSON.stringify({ items: [], total: 0, limit: 10, offset: 0 })))))
    mount()
    await screen.findByText("Backend działa")
    await userEvent.click(screen.getByRole("link", { name: "Sesje" }))
    expect(screen.getByRole("heading", { name: "Sesje" })).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Nowa sesja" })).toBeInTheDocument()
    await userEvent.click(screen.getByRole("link", { name: "Graf witryny" }))
    expect(await screen.findByRole("heading", { name: "Graf witryny" })).toBeInTheDocument()
    await userEvent.click(screen.getByRole("link", { name: "Porównania" }))
    expect(await screen.findByRole("heading", { name: "Porównania i eksperymenty" })).toBeInTheDocument()
  })

  it("aborts pending request on unmount", async () => {
    let signal: AbortSignal | undefined
    vi.stubGlobal("fetch", vi.fn((_url, options: RequestInit) => {
      signal = options.signal as AbortSignal
      return new Promise(() => {})
    }))
    const view = mount()
    await waitFor(() => expect(signal).toBeDefined())
    view.unmount()
    expect(signal?.aborted).toBe(true)
  })
})
