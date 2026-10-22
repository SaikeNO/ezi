import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { request } from "@/lib/sessions-api";
import { statusLabels, type CrawlSession, type SessionStatus } from "@/types/sessions";

export interface DashboardData {
  sessions: number; statuses: Record<SessionStatus, number>; discovered_pages: number;
  fetched_pages: number; errored_pages: number; links: number; recent: CrawlSession[];
}
export function Dashboard() {
  const [data, setData] = useState<DashboardData>();
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setError(""); setData(undefined);
    request<DashboardData>("/api/dashboard", { signal: controller.signal }).then(value => {
      if (![value.sessions, value.discovered_pages, value.fetched_pages, value.errored_pages, value.links].every(n => Number.isInteger(n) && n >= 0)
        || !value.statuses || !Array.isArray(value.recent)
        || !Object.keys(statusLabels).every(key => Number.isInteger(value.statuses[key as SessionStatus]) && value.statuses[key as SessionStatus] >= 0)
        || !value.recent.every(run => typeof run.id === "string" && typeof run.start_url === "string" && run.status in statusLabels)) {
        throw new Error("Nieprawidłowa odpowiedź dashboardu.");
      }
      if (!controller.signal.aborted) setData(value);
    }).catch(err => { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "Błąd odczytu."); });
    return () => controller.abort();
  }, [refresh]);
  return <section aria-label="Dashboard zapisanych wyników" className="mt-8 rounded-2xl border bg-white p-6">
    <h2 className="text-xl font-semibold">Zapisane wyniki</h2>
    <p className="my-3 text-sm text-muted-foreground">Snapshot całej bazy. Sumy obejmują osobne sesje; ten sam URL może wystąpić wielokrotnie. Odśwież, aby zobaczyć postęp.</p>
    <Button variant="outline" onClick={() => setRefresh(n => n + 1)}>Odśwież dashboard</Button>
    {error ? <p role="alert" className="mt-4 text-red-800">{error}</p> : !data ? <p className="mt-4">Wczytywanie wyników…</p> : <>
      <dl className="my-6 grid grid-cols-2 gap-4 sm:grid-cols-3">{[
        ["Sesje", data.sessions], ["Odkryte strony", data.discovered_pages], ["Pobrane HTML", data.fetched_pages],
        ["Linki", data.links], ["Strony z błędami", data.errored_pages],
      ].map(([label, count]) => <div key={label}><dt className="text-sm text-muted-foreground">{label}</dt><dd className="text-2xl font-semibold">{count}</dd></div>)}</dl>
      <ul className="flex flex-wrap gap-4 text-sm">{Object.entries(data.statuses).map(([status, count]) => <li key={status}>{statusLabels[status as SessionStatus]}: {count}</li>)}</ul>
      <h3 className="mt-6 font-semibold">Ostatnie 5 sesji</h3>
      {data.recent.length ? <ul className="mt-3 space-y-3">{data.recent.map(run => <li key={run.id} className="break-all"><Link className="text-teal-800 underline" to={`/sessions/${run.id}`}>{run.start_url}</Link> — {statusLabels[run.status]}</li>)}</ul> : <p className="mt-3">Brak sesji. <Link className="underline" to="/sessions">Utwórz pierwszą sesję</Link>.</p>}
    </>}
  </section>;
}
