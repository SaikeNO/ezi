import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, CartesianGrid, ResponsiveContainer } from "recharts";
import { Button } from "@/components/ui/button";
import { comparisonApi, type Comparison, type Results, type RunMetrics, type UrlSets } from "@/lib/comparison-api";
import { statusLabels } from "@/types/sessions";

const labels = ["A", "B", "C", "D"];
export function MetricsCharts({ runs }: { runs: RunMetrics[] }) {
  const counts = runs.map((run, index) => ({ name: labels[index], fetched: run.fetched_pages,
    discovered: run.discovered_pages, links: run.link_count }));
  const times = runs.flatMap((run, index) => run.elapsed_seconds === null ? [] : [{ name: labels[index], seconds: run.elapsed_seconds }]);
  return <div className="my-6 grid min-w-0 gap-5 lg:grid-cols-2">
    <section className="min-w-0 rounded-xl border bg-white p-4" aria-label="Wykres liczników"><h3 className="font-medium">Zapisane strony i linki</h3>
      <div className="mt-3 h-72"><ResponsiveContainer width="100%" height="100%" minWidth={0}><BarChart data={counts} accessibilityLayer>
        <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" /><YAxis allowDecimals={false} /><Tooltip /><Legend />
        <Bar dataKey="discovered" name="Odkryte" fill="#94a3b8" isAnimationActive={false} />
        <Bar dataKey="fetched" name="Pobrane HTML" fill="#0f766e" isAnimationActive={false} />
        <Bar dataKey="links" name="Linki" fill="#6366f1" isAnimationActive={false} />
      </BarChart></ResponsiveContainer></div>
    </section>
    <section className="min-w-0 rounded-xl border bg-white p-4" aria-label="Wykres czasu"><h3 className="font-medium">Zmierzony czas sesji (s)</h3>
      {times.length ? <div className="mt-3 h-72"><ResponsiveContainer width="100%" height="100%" minWidth={0}><BarChart data={times} accessibilityLayer>
        <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="name" /><YAxis /><Tooltip /><Bar dataKey="seconds" name="Sekundy" fill="#b45309" isAnimationActive={false} />
      </BarChart></ResponsiveContainer></div> : <p className="mt-4">Brak zapisanych czasów startu i zakończenia.</p>}
    </section>
  </div>;
}

function Items<T>({ title, data, render }: { title: string; data: Results<T>; render: (value: T) => ReactNode }) {
  return <details className="mt-3 rounded-lg border bg-white p-3"><summary className="cursor-pointer text-sm font-medium">{title}: {data.total}</summary>
    {data.items.length ? <ul className="mt-3 max-h-72 space-y-3 overflow-y-auto text-sm">{data.items.map((value, index) => <li key={index} className="break-all border-t pt-2">{render(value)}</li>)}</ul> : <p className="mt-3 text-sm">Brak elementów w tej partii.</p>}
  </details>;
}
function Sets({ title, data }: { title: string; data: UrlSets }) {
  return <section className="mt-5"><h4 className="font-semibold">{title}</h4>
    <Items title="Wspólne" data={data.common} render={value => value} />
    <Items title="Tylko A" data={data.left_only} render={value => value} />
    <Items title="Tylko B" data={data.right_only} render={value => value} />
  </section>;
}

function maxTotal(data: Comparison) {
  return Math.max(0, ...data.runs.map(run => run.retrieval_order.total), ...data.pairs.flatMap(pair => [
    ...Object.values(pair.discovered).map(value => value.total), ...Object.values(pair.fetched).map(value => value.total),
    ...Object.values(pair.edges).map(value => value.total), pair.metadata_changes.total, pair.depth_changes.total,
  ]));
}

export function ComparisonResults({ ids }: { ids: string[] }) {
  const signature = ids.join(",");
  const [offset, setOffset] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [data, setData] = useState<Comparison | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController(); setData(null); setError("");
    comparisonApi.compare(signature.split(","), offset, controller.signal).then(data => {
      if (!controller.signal.aborted) setData(data);
    }, error => { if (!controller.signal.aborted) setError(error instanceof Error ? error.message : "Błąd porównania"); });
    return () => controller.abort();
  }, [signature, offset, attempt]);
  return <section className="mt-8 min-w-0" aria-label="Porównanie sesji">
    <h2 className="text-2xl font-semibold">Porównanie zapisanych wyników</h2>
    {error && <div className="mt-5"><p role="alert">{error}</p><Button className="mt-3" onClick={() => setAttempt(value => value + 1)}>Ponów porównanie</Button></div>}
    {!data && !error && <p role="status" className="mt-5">Obliczanie porównania…</p>}
    {data && <>
      <p className="mt-4 break-all text-sm">Wspólny adres startowy: {data.start_url}</p>
      <ul className="mt-4 space-y-2 rounded-xl bg-amber-50 p-4 text-sm text-amber-950">{data.notes.map(note => <li key={note}>{note}</li>)}</ul>
      <MetricsCharts runs={data.runs} />
      <div className="overflow-x-auto rounded-xl border bg-white p-4" tabIndex={0} aria-label="Tabela metryk — przewiń poziomo"><table className="w-full min-w-[850px] text-left text-sm [&_td]:px-3 [&_td]:py-3 [&_th]:px-3">
        <caption className="mb-4 text-left font-semibold">Metryki z zapisanych stron, linków i czasów</caption>
        <thead><tr>{["Wariant / status", "Odkryte", "Pobrane HTML", "Próby / błędy", "Linki / różne typowane", "Głębokość HTML", "Czas (s)"].map(value => <th key={value}>{value}</th>)}</tr></thead>
        <tbody>{data.runs.map((run, index) => <tr key={run.session.id} className="border-t"><td><Link to={"/sessions/" + run.session.id} className="text-teal-800 underline">{labels[index]}</Link> · {statusLabels[run.session.status]}<p className="text-xs">{run.session.stop_reason}</p></td><td>{run.discovered_pages}</td><td>{run.fetched_pages}</td><td>{run.attempted_pages} / {run.errored_pages}</td><td>{run.link_count} / {run.unique_typed_edges}</td><td>{run.reached_depth ?? "—"}</td><td>{run.elapsed_seconds === null ? "—" : run.elapsed_seconds.toFixed(3)}</td></tr>)}</tbody>
      </table></div>
      {data.runs.map((run, index) => <details key={run.session.id} className="mt-3 rounded-xl border bg-white p-4"><summary className="cursor-pointer font-medium">Wariant {labels[index]} — konfiguracja, kompletność, kolejność</summary>
        <p className="my-3 break-all text-xs">ID: {run.session.id} · crawler {run.session.crawler_version ?? "brak"} · {run.session.user_agent ?? "brak UA"}</p>
        <dl className="grid gap-2 text-sm sm:grid-cols-2">{Object.entries(run.session.config).map(([key, value]) => <div key={key}><dt className="text-muted-foreground">{key}</dt><dd>{String(value)}</dd></div>)}</dl>
        <p className="mt-4 text-sm">Pola obecne (null oznacza brak, pusty tekst jest obecny): {Object.entries(run.metadata_present).map(([key, value]) => key + ": " + value).join(" · ")}</p>
        <Items title="Kolejność prób pobrania" data={run.retrieval_order} render={value => value} />
      </details>)}
      {data.pairs.map((pair, index) => <section key={pair.right_id} className="mt-8 rounded-2xl border bg-card p-5">
        <h3 className="text-xl font-semibold">A względem {labels[index + 1]}</h3>
        <p className="mt-2 text-sm">W listach poniżej B oznacza wariant {labels[index + 1]}. Krawędź: źródło → cel + rodzaj; powtórzenia liczone oddzielnie.</p>
        <p className="mt-3 text-sm">Kolejność prób {pair.retrieval_order_equal ? "identyczna" : "różna"}.</p>
        <ul className="my-4 space-y-2 text-sm">{pair.observations.map(value => <li key={value}>{value}</li>)}</ul>
        <h4 className="font-semibold">Zmienione parametry</h4>
        {Object.entries(pair.config_changes).length ? <ul className="mt-2 text-sm">{Object.entries(pair.config_changes).map(([key, values]) => <li key={key}>{key}: {String(values[0])} → {String(values[1])}</li>)}</ul> : <p className="mt-2 text-sm">Identyczna konfiguracja.</p>}
        <Sets title="Zbiory odkrytych URL" data={pair.discovered} /><Sets title="Zbiory pobranych HTML" data={pair.fetched} />
        <h4 className="mt-5 font-semibold">Typowane krawędzie</h4>
        <Items title="Wspólne krawędzie" data={pair.edges.common} render={value => <>{value.source} → {value.target} ({value.kind})</>} />
        <Items title="Krawędzie tylko A" data={pair.edges.left_only} render={value => <>{value.source} → {value.target} ({value.kind})</>} />
        <Items title="Krawędzie tylko B" data={pair.edges.right_only} render={value => <>{value.source} → {value.target} ({value.kind})</>} />
        <Items title="Różnice liczby wystąpień" data={pair.edges.multiplicity_changes} render={value => <>{value.source} → {value.target} ({value.kind}): A {value.left_count}, B {value.right_count}</>} />
        <Items title="Zmiany głębokości odkrytych stron" data={pair.depth_changes} render={value => <>{value.url}: {value.left} → {value.right}</>} />
        <Items title="Zmiany metadanych wspólnie pobranych HTML" data={pair.metadata_changes} render={change => <><strong>{change.url}</strong>{Object.entries(change.fields).map(([field, values]) => <div key={field} className="mt-3"><p className="font-medium">{field}</p>{values.map((value, idx) => <div key={idx} className="mt-2 rounded bg-slate-50 p-3"><span className="font-medium">{idx ? "B" : "A"}: </span>{value.value === null ? "Brak (null)" : value.value || "(puste)"}<p className="mt-1 text-xs">Długość: {value.length ?? "—"} · SHA-256: {value.sha256 ?? "—"}{value.truncated ? " · Podgląd pierwszych 500 znaków; skrót obejmuje całość." : ""}</p></div>)}</div>)}</>} />
      </section>)}
      <div className="mt-6 flex flex-wrap items-center gap-3"><Button variant="outline" disabled={offset === 0} onClick={() => setOffset(value => Math.max(0, value - 25))}>Poprzednia partia</Button><span className="text-sm">Listy: pozycje {offset + 1}–{offset + 25}; liczniki obejmują całość.</span><Button variant="outline" disabled={offset + 25 >= maxTotal(data)} onClick={() => setOffset(value => value + 25)}>Następna partia</Button></div>
    </>}
  </section>;
}
