import { useEffect, useState } from "react"
import { Activity, RefreshCw } from "lucide-react"
import { Button } from "@/components/ui/button"
import { fetchHealth, type HealthResponse } from "@/lib/api"

type State = { kind: "loading" | "error" } | { kind: "received"; health: HealthResponse }

export function HealthPanel() {
  const [state, setState] = useState<State>({ kind: "loading" })
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    setState({ kind: "loading" })
    fetchHealth(controller.signal).then(
      health => { if (!controller.signal.aborted) setState({ kind: "received", health }) },
      () => { if (!controller.signal.aborted) setState({ kind: "error" }) },
    )
    return () => controller.abort()
  }, [attempt])

  const ready = state.kind === "received" && state.health.status === "ok"
  const message = state.kind === "loading" ? "Sprawdzanie połączenia…"
    : state.kind === "error" ? "Brak połączenia z backendem"
    : ready ? "Backend działa" : "Backend odpowiada — baza danych niedostępna"
  return (
    <section aria-labelledby="connection-heading" className="rounded-2xl border bg-card p-6 shadow-sm sm:p-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div><p className="eyebrow">POŁĄCZENIE Z SYSTEMEM</p><h2 id="connection-heading" className="mt-2 text-xl font-semibold">Status usług</h2></div>
        <Activity aria-hidden="true" className="text-teal-700" />
      </div>
      <div role="status" aria-live="polite" className="my-7 flex items-center gap-3">
        <span className={`h-3 w-3 shrink-0 rounded-full ${state.kind === "loading" ? "bg-slate-400" : ready ? "bg-teal-600" : "bg-amber-500"}`} />
        <span className="font-medium">{message}</span>
      </div>
      {state.kind === "received" && <p className="mb-6 text-sm text-muted-foreground">SQLite: {state.health.database === "ok" ? "połączenie aktywne" : "niedostępna"}</p>}
      {state.kind === "error" && <p className="mb-6 text-sm text-muted-foreground">Sprawdź, czy serwer API jest uruchomiony i adres API jest poprawny.</p>}
      <Button variant="outline" disabled={state.kind === "loading"} onClick={() => setAttempt(value => value + 1)}>
        <RefreshCw aria-hidden="true" /> Sprawdź ponownie
      </Button>
    </section>
  )
}
