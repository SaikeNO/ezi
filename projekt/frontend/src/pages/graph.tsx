import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { GraphCanvas } from "@/components/graph-canvas";
import { Button } from "@/components/ui/button";
import { ApiError, graphApi, sessionsApi } from "@/lib/sessions-api";
import { statusLabels, type SessionList } from "@/types/sessions";
import type { GraphNode, GraphRead, GraphSummary, PageDetail } from "@/types/graph";

const message = (error: unknown) => error instanceof Error ? error.message : "Nie udało się odczytać grafu.";
const metricLabels: Record<keyof GraphSummary, string> = {
  node_count: "Węzły", page_count: "Odkryte strony", resource_target_count: "Pozostałe cele",
  fetched_pages: "Pobrane HTML", errored_pages: "Strony z błędem", reached_depth: "Osiągnięta głębokość HTML",
  discovered_depth: "Głębokość odkrytych stron", link_count: "Wystąpienia linków",
  unique_relations: "Unikalne relacje", internal_links: "Linki wewnętrzne", external_links: "Linki zewnętrzne",
  root_links: "Linki strony startowej", root_unique_targets: "Unikalne cele strony startowej",
  subpage_links: "Linki podstron", subpage_unique_targets: "Unikalne cele podstron",
};

export function GraphMetrics({ graph }: { graph: GraphRead }) {
  return <section aria-label="Statystyki grafu" className="my-7 rounded-2xl border bg-card p-5">
    <h2 className="text-xl font-semibold">Statystyki zapisanej sesji</h2>
    <dl className="mt-5 grid grid-cols-2 gap-5 md:grid-cols-3 xl:grid-cols-4">
      {Object.entries(graph.summary).map(([key, value]) => <div key={key}>
        <dt className="text-xs text-muted-foreground">{metricLabels[key as keyof GraphSummary]}</dt>
        <dd className="mt-1 text-xl font-semibold tabular-nums">{value ?? "—"}</dd>
      </div>)}
    </dl>
    <p className="mt-5 text-xs text-muted-foreground">Relacja = unikalna para źródło → cel, niezależnie od rodzaju. Stopnie liczą wystąpienia; unikalne stopnie liczą sąsiadów. Pętla liczy się raz w każdym kierunku. Głębokość HTML obejmuje tylko pobrane strony.</p>
    {graph.per_depth.length > 0 && <div className="mt-5 overflow-x-auto" tabIndex={0} aria-label="Tabela poziomów — przewiń poziomo"><table className="w-full min-w-[400px] text-left text-sm [&_th]:pr-4 [&_td]:pr-4">
      <caption className="mb-2 text-left font-medium">Strony według głębokości</caption>
      <thead><tr><th>Poziom</th><th>Odkryte</th><th>Pobrane HTML</th><th>Linki wychodzące</th></tr></thead>
      <tbody>{graph.per_depth.map(level => <tr key={level.depth} className="border-t">
        <td className="py-2">{level.depth}</td><td>{level.pages}</td><td>{level.fetched_pages}</td><td>{level.outgoing_links}</td>
      </tr>)}</tbody>
    </table></div>}
  </section>;
}

function NodeDetails({ sessionId, node }: { sessionId: string; node: GraphNode }) {
  const [detail, setDetail] = useState<PageDetail | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setDetail(null); setError("");
    if (node.page_id) graphApi.page(sessionId, node.page_id, controller.signal).then(data => {
      if (!controller.signal.aborted) setDetail(data);
    }, error => { if (!controller.signal.aborted) setError(message(error)); });
    return () => controller.abort();
  }, [sessionId, node.page_id, attempt]);
  return <section aria-label="Szczegóły węzła" className="mt-6 rounded-2xl border bg-card p-5">
    <h2 className="text-xl font-semibold">Szczegóły węzła</h2>
    <p className="mt-3 break-all font-medium">{node.url}</p>
    <dl className="mt-4 grid grid-cols-2 gap-4 text-sm">
      {Object.entries({ "Rodzaj": node.page_id ? "Strona" : "Cel zasobu", "Poziom": node.depth,
        "Pobrany HTML": node.fetched ? "Tak" : "Nie", "HTTP": node.http_status ?? "—",
        "In-degree": node.in_degree, "Out-degree": node.out_degree,
        "Unikalne in-degree": node.unique_in_degree, "Unikalne out-degree": node.unique_out_degree,
      }).map(([label, value]) => <div key={label}><dt className="text-muted-foreground">{label}</dt><dd>{value}</dd></div>)}
    </dl>
    {node.error && <p className="mt-4 break-all text-red-800">{node.error}</p>}
    {!node.page_id && <p className="mt-4 text-sm">Cel odnośnika bez rekordu strony. Poziom oznacza najmniejszy poziom źródła + 1; zasób nie został pobrany jako HTML.</p>}
    {node.page_id && !detail && !error && <p role="status" className="mt-4">Wczytywanie metadanych…</p>}
    {error && <div className="mt-4"><p role="alert">{error}</p><Button variant="outline" onClick={() => setAttempt(value => value + 1)}>Ponów odczyt metadanych</Button></div>}
    {detail && <dl className="mt-5 space-y-4 text-sm">
      {Object.entries({ "Tytuł": detail.title, "Opis": detail.description, "Słowa kluczowe": detail.keywords,
        "Końcowy URL": detail.final_url, "Content-Type": detail.content_type, "Kodowanie": detail.encoding,
      }).map(([label, value]) => <div key={label}><dt className="text-muted-foreground">{label}</dt><dd className="break-all">{value === null ? "Brak" : value || "(puste)"}</dd></div>)}
      <div><dt className="text-muted-foreground">Tekst body</dt><dd className="mt-2 max-h-64 overflow-y-auto whitespace-pre-wrap break-words">{detail.body === null ? "Brak zapisanej treści" : detail.body || "(puste)"}</dd></div>
    </dl>}
  </section>;
}

function GraphSession({ id }: { id: string }) {
  const [state, setState] = useState<{ graph: GraphRead; limited: boolean } | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    setState(null); setError(""); setSelected(null);
    async function load() {
      try {
        const graph = await graphApi.graph(id, controller.signal);
        if (!controller.signal.aborted) setState({ graph, limited: false });
      } catch (error) {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === 413) {
          try {
            const stats = await graphApi.stats(id, controller.signal);
            if (!controller.signal.aborted) setState({ graph: { ...stats, nodes: [], edges: [] }, limited: true });
          } catch (fallbackError) {
            if (!controller.signal.aborted) setError(message(fallbackError));
          }
        } else setError(message(error));
      }
    }
    void load();
    return () => controller.abort();
  }, [id, attempt]);
  const graph = state?.graph;
  const selectedNode = graph?.nodes.find(node => node.id === selected);
  const matches = graph?.nodes.filter(node => (node.url + " " + (node.title ?? "")).toLocaleLowerCase("pl").includes(query.toLocaleLowerCase("pl"))) ?? [];
  return <>
    <div className="mt-5 flex flex-wrap gap-4"><Link to={"/sessions/" + id} className="text-teal-800 underline">Szczegóły sesji</Link>
      <Button variant="outline" onClick={() => setAttempt(value => value + 1)}>Odśwież graf</Button></div>
    {error && <p role="alert" className="mt-6">{error}</p>}
    {!state && !error && <p role="status" className="mt-6">Wczytywanie grafu…</p>}
    {graph && <>
      <p className="mt-4 text-sm text-muted-foreground">Stan sesji: {statusLabels[graph.status]}. Widok jest zapisanym odczytem; odśwież, aby pobrać nowsze wyniki.</p>
      <GraphMetrics graph={graph} />
      {state.limited ? <p role="alert">Graf przekracza limit 5000 węzłów lub 20000 linków. Pokazano pełne statystyki. Utwórz mniejszą sesję, aby zobaczyć wizualizację.</p>
      : graph.nodes.length === 0 ? <p>Brak zapisanych węzłów. Uruchom crawler w szczegółach sesji.</p>
      : <>
        <GraphCanvas graph={graph} selected={selected} onSelect={setSelected} />
        <section className="mt-6 rounded-2xl border bg-white p-5" aria-label="Wyszukiwanie węzłów">
          <label className="block text-sm font-medium">Szukaj węzła po URL lub tytule
            <input value={query} onChange={event => setQuery(event.target.value)} className="mt-2 block w-full rounded-lg border p-3" />
          </label>
          <p className="mt-2 text-sm text-muted-foreground">Pasujące węzły: {matches.length}. Lista pokazuje pierwsze 30; zawęź wyszukiwanie.</p>
          <ul className="mt-3 max-h-56 space-y-2 overflow-y-auto">{matches.slice(0, 30).map(node => <li key={node.id}>
            <button type="button" aria-pressed={selected === node.id} onClick={() => setSelected(node.id)} className="w-full break-all rounded-lg border px-3 py-2 text-left text-sm hover:bg-teal-50 aria-pressed:bg-teal-100">{node.url}</button>
          </li>)}</ul>
          {matches.length === 0 && <p className="mt-3">Brak pasujących węzłów.</p>}
        </section>
        {selectedNode ? <NodeDetails key={selectedNode.id} sessionId={id} node={selectedNode} /> : <p className="mt-5 text-sm">Wybierz węzeł na grafie lub liście, aby zobaczyć metadane i stopnie.</p>}
      </>}
    </>}
  </>;
}

function GraphChooser() {
  const [data, setData] = useState<SessionList | null>(null);
  const [offset, setOffset] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController(); setData(null); setError("");
    sessionsApi.list(offset, "", controller.signal).then(data => {
      if (!controller.signal.aborted) setData(data);
    }, error => { if (!controller.signal.aborted) setError(message(error)); });
    return () => controller.abort();
  }, [offset, attempt]);
  return <section className="mt-7 rounded-2xl border bg-white p-5">
    <h2 className="text-xl font-semibold">Wybierz zapisaną sesję</h2>
    {error && <div><p role="alert">{error}</p><Button onClick={() => setAttempt(value => value + 1)}>Spróbuj ponownie</Button></div>}
    {!data && !error && <p role="status" className="mt-4">Wczytywanie sesji…</p>}
    {data && <>
      {data.items.length === 0 && <p className="mt-4">Brak zapisanych sesji. <Link to="/sessions" className="underline">Utwórz sesję</Link>.</p>}
      <ul className="my-5 space-y-3">{data.items.map(session => <li key={session.id}><Link to={"/graph/" + session.id} className="block break-all rounded-lg border p-3 text-sm text-teal-800 hover:bg-teal-50">{session.start_url} · {statusLabels[session.status]} · {session.created_at}</Link></li>)}</ul>
      <div className="flex flex-wrap items-center gap-3"><Button variant="outline" disabled={offset === 0} onClick={() => setOffset(value => Math.max(0, value - 10))}>Poprzednie</Button>
        <span className="text-sm">Łącznie: {data.total}</span><Button variant="outline" disabled={offset + 10 >= data.total} onClick={() => setOffset(value => value + 10)}>Następne</Button></div>
    </>}
  </section>;
}

export function GraphPage() {
  const { id } = useParams();
  return <><p className="eyebrow">RZECZYWISTE STRONY I RELACJE</p><h1 className="mt-3 text-3xl font-semibold">Graf witryny</h1>
    <p className="mt-4 text-muted-foreground">Skierowany graf zapisanych wyników. Cele zasobów i niepobrane strony pozostają widoczne. BFS/DFS określa kolejność pobierania; pełny zbiór osiągalnych stron może być taki sam.</p>
    {id ? <GraphSession key={id} id={id} /> : <GraphChooser />}</>;
}
