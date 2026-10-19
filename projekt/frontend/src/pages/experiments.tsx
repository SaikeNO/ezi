import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ComparisonResults } from "@/components/comparison-results";
import { comparisonApi, type Experiment } from "@/lib/comparison-api";
import { sessionsApi } from "@/lib/sessions-api";
import { defaultConfig, statusLabels, type CrawlConfig, type CrawlSession, type SessionList } from "@/types/sessions";

const message = (error: unknown) => error instanceof Error ? error.message : "Nie udało się odczytać eksperymentu.";
const inputClass = "mt-2 block w-full rounded-lg border bg-white p-2 text-sm";
const numberFields = [
  ["max_depth", "Głębokość", 0, 20], ["max_pages", "Limit stron", 1, 10000],
  ["request_delay_ms", "Opóźnienie (ms)", 100, 60000], ["timeout_seconds", "Czas żądania (s)", 1, 60],
  ["max_duration_seconds", "Czas sesji (s)", 1, 3600], ["max_response_bytes", "Limit bajtów", 1024, 10485760],
  ["max_redirects", "Limit przekierowań", 0, 10], ["concurrency", "Współbieżność (górna granica)", 1, 8],
] as const;

function ExperimentForm() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [variants, setVariants] = useState<CrawlConfig[]>([{ ...defaultConfig }, { ...defaultConfig, strategy: "dfs" }]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const setConfig = (index: number, key: keyof CrawlConfig, value: string | number | boolean) => setVariants(current => current.map((config, position) => position === index ? { ...config, [key]: value } : config));
  return <form className="mt-7 rounded-2xl border bg-card p-5" onSubmit={async event => {
    event.preventDefault(); setBusy(true); setError("");
    try { const saved = await comparisonApi.create(name, url, variants); navigate("/experiments/" + saved.id); }
    catch (error) { setError(message(error)); setBusy(false); }
  }}>
    <h2 className="text-xl font-semibold">Nowy eksperyment</h2>
    <p className="mt-3 text-sm text-muted-foreground">Od 2 do 4 niezależnych wariantów jednego URL. Domyślnie różnią się BFS/DFS. Utworzenie zapisuje konfiguracje; uruchomisz je w szczegółach. Każdy wariant pobiera sekwencyjnie.</p>
    <div className="mt-5 grid gap-4 sm:grid-cols-2"><label className="text-sm">Nazwa eksperymentu<input required maxLength={200} value={name} onChange={event => setName(event.target.value)} className={inputClass} /></label>
      <label className="text-sm">Wspólny adres startowy<input required type="url" maxLength={2048} value={url} onChange={event => setUrl(event.target.value)} className={inputClass} /></label></div>
    <div className="mt-6 grid gap-5 lg:grid-cols-2">{variants.map((config, index) => <fieldset key={index} disabled={busy} className="min-w-0 rounded-xl border p-4"><legend className="px-2 font-semibold">Wariant {String.fromCharCode(65 + index)}</legend>
      <label className="block text-sm">Strategia<select value={config.strategy} onChange={event => setConfig(index, "strategy", event.target.value)} className={inputClass}><option value="bfs">BFS</option><option value="dfs">DFS</option></select></label>
      <label className="mt-4 block text-sm">Zakres<select value={config.scope} onChange={event => setConfig(index, "scope", event.target.value)} className={inputClass}><option value="server">Ten sam host (server)</option><option value="web">Sieć WWW (web)</option></select></label>
      <label className="mt-4 block text-sm">Rodzaje linków<select value={config.link_types} onChange={event => setConfig(index, "link_types", event.target.value)} className={inputClass}><option value="hyperlinks">Hiperłącza</option><option value="images_and_hyperlinks">Obrazy i hiperłącza</option><option value="all_links">Wszystkie obsługiwane</option></select></label>
      <div className="mt-4 grid gap-4 sm:grid-cols-2">{numberFields.slice(0, 3).map(([key, label, min, max]) => <label key={key} className="text-sm">{label}<input required type="number" min={min} max={max} value={config[key]} onChange={event => setConfig(index, key, event.target.valueAsNumber)} className={inputClass} /></label>)}</div>
      <div className="mt-4 space-y-3">{([["respect_robots", "Respektuj robots.txt"], ["follow_external_urls", "Podążaj za zewnętrznymi (tylko web)"], ["process_one_page", "Tylko strona startowa"]] as const).map(([key, label]) => <label className="block text-sm" key={key}><input type="checkbox" checked={config[key]} onChange={event => setConfig(index, key, event.target.checked)} className="mr-2" />{label}</label>)}</div>
      <details className="mt-4"><summary className="cursor-pointer text-sm">Pozostałe limity</summary><div className="mt-4 grid gap-4 sm:grid-cols-2">{numberFields.slice(3).map(([key, label, min, max]) => <label key={key} className="text-sm">{label}<input required type="number" min={min} max={max} step={key === "timeout_seconds" ? 0.1 : 1} value={config[key]} onChange={event => setConfig(index, key, event.target.valueAsNumber)} className={inputClass} /></label>)}</div></details>
    </fieldset>)}</div>
    <div className="mt-5 flex flex-wrap gap-3"><Button type="button" variant="outline" disabled={busy || variants.length >= 4} onClick={() => setVariants(current => [...current, { ...defaultConfig }])}>Dodaj wariant</Button><Button type="button" variant="outline" disabled={busy || variants.length <= 2} onClick={() => setVariants(current => current.slice(0, -1))}>Usuń ostatni wariant</Button><Button disabled={busy} type="submit">{busy ? "Zapisywanie…" : "Utwórz eksperyment"}</Button></div>
    {error && <p role="alert" className="mt-4">{error}</p>}
  </form>;
}

function ExperimentList() {
  const [data, setData] = useState<Awaited<ReturnType<typeof comparisonApi.list>> | null>(null);
  const [offset, setOffset] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController(); setData(null); setError("");
    comparisonApi.list(offset, controller.signal).then(data => { if (!controller.signal.aborted) setData(data); }, error => { if (!controller.signal.aborted) setError(message(error)); });
    return () => controller.abort();
  }, [offset, attempt]);
  return <section className="mt-7 rounded-2xl border bg-card p-5"><h2 className="text-xl font-semibold">Zapisane eksperymenty</h2>
    {error && <><p role="alert">{error}</p><Button onClick={() => setAttempt(value => value + 1)}>Ponów listę eksperymentów</Button></>}
    {!data && !error && <p role="status" className="mt-4">Wczytywanie eksperymentów…</p>}
    {data && <>{!data.items.length && <p className="mt-4">Brak zapisanych eksperymentów.</p>}<ul className="my-4 space-y-3">{data.items.map(item => <li key={item.id}><Link className="block break-all rounded-lg border p-3 text-teal-800" to={"/experiments/" + item.id}>{item.name} · {item.start_url} · warianty: {item.sessions.length}</Link></li>)}</ul>
      <div className="flex flex-wrap gap-3"><Button variant="outline" disabled={!offset} onClick={() => setOffset(value => Math.max(0, value - 10))}>Poprzednie eksperymenty</Button><span>Łącznie: {data.total}</span><Button variant="outline" disabled={offset + 10 >= data.total} onClick={() => setOffset(value => value + 10)}>Następne eksperymenty</Button></div></>}
  </section>;
}

function SavedSessionComparison() {
  const [data, setData] = useState<SessionList | null>(null);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [selected, setSelected] = useState<CrawlSession[]>([]);
  const [ids, setIds] = useState<string[] | null>(null);
  useEffect(() => {
    const controller = new AbortController(); setData(null); setError("");
    sessionsApi.list(offset, "", controller.signal).then(data => { if (!controller.signal.aborted) setData(data); }, error => { if (!controller.signal.aborted) setError(message(error)); });
    return () => controller.abort();
  }, [offset, attempt]);
  return <section className="mt-7 min-w-0 rounded-2xl border bg-card p-5" aria-label="Porównaj istniejące sesje">
    <h2 className="text-xl font-semibold">Porównaj istniejące sesje</h2><p className="mt-3 text-sm">Wybierz 2–4 zakończone sesje z tym samym URL. Pierwsza jest bazą A. Wyniki failed/cancelled są częściowe.</p>
    {error && <p role="alert">{error}</p>}{!data && !error && <p role="status" className="mt-3">Wczytywanie sesji…</p>}
    {data && <><ul className="my-4 space-y-3">{data.items.map(item => {
      const checked = selected.some(value => value.id === item.id);
      const disabled = !checked && (item.status === "queued" || item.status === "running" || selected.length >= 4 || (selected.length > 0 && item.start_url !== selected[0].start_url));
      return <li key={item.id}><label className="block break-all rounded-lg border p-3 text-sm"><input type="checkbox" checked={checked} disabled={disabled} className="mr-2" onChange={event => { setIds(null); setSelected(current => event.target.checked ? [...current, item] : current.filter(value => value.id !== item.id)); }} />{item.start_url} · {statusLabels[item.status]} · {item.created_at} · {item.id}</label></li>;
    })}</ul><div className="flex flex-wrap gap-3"><Button variant="outline" disabled={!offset} onClick={() => setOffset(value => Math.max(0, value - 10))}>Poprzednie sesje</Button><Button variant="outline" disabled={offset + 10 >= data.total} onClick={() => setOffset(value => value + 10)}>Następne sesje</Button></div></>}
    <p className="my-4 break-all text-sm">Wybrane: {selected.map((item, index) => String.fromCharCode(65 + index) + " " + item.id).join(" · ") || "brak"}</p>
    <div className="flex flex-wrap gap-3"><Button disabled={selected.length < 2} onClick={() => setIds(selected.map(item => item.id))}>Porównaj wybrane sesje</Button><Button variant="outline" onClick={() => { setSelected([]); setIds(null); }}>Wyczyść wybór</Button><Button variant="outline" onClick={() => setAttempt(value => value + 1)}>Odśwież sesje</Button></div>
    {ids && <ComparisonResults key={ids.join(",")} ids={ids} />}
  </section>;
}

function ExperimentDetail({ id }: { id: string }) {
  const navigate = useNavigate();
  const [data, setData] = useState<Experiment | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [launchErrors, setLaunchErrors] = useState<string[]>([]);
  const [showComparison, setShowComparison] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  useEffect(() => {
    if (busy) return;
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout> | undefined;
    const load = async () => {
      try { const value = await comparisonApi.read(id, controller.signal); if (!controller.signal.aborted) {
        setData(value); setError(""); if (value.state === "running") timer = setTimeout(load, 1000);
      } } catch (error) { if (!controller.signal.aborted) setError(message(error)); }
    };
    void load();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [id, attempt, busy]);
  return <>
    <Link className="mt-4 inline-block text-teal-800 underline" to="/experiments">Wróć do eksperymentów</Link>
    {error && <p role="alert" className="mt-4">{error}</p>}
    {!data && !error && <p role="status" className="mt-4">Wczytywanie eksperymentu…</p>}
    {data && <><h2 className="mt-6 break-all text-2xl font-semibold">{data.name}</h2><p className="mt-2 break-all">{data.start_url}</p>
      <p className="mt-4 text-sm text-muted-foreground">Każdy wariant to niezależna sesja. Usunięcie sesji usuwa ją z eksperymentu. Nie wznowimy zadań po awarii; utwórz nowy eksperyment dla powtórzenia pomiaru.</p>
      {data.state === "incomplete" && <p role="alert" className="mt-4">Pozostało mniej niż 2 warianty. Eksperyment niekompletny.</p>}
      <div className="mt-5 flex flex-wrap gap-3"><Button disabled={busy || data.state === "incomplete" || !data.sessions.some(item => item.status === "queued")} onClick={async () => {
        setBusy(true); setError(""); setLaunchErrors([]); setShowComparison(false);
        try { const result = await comparisonApi.start(id); setData(result.experiment); setLaunchErrors(result.errors.map(value => value.session_id + ": " + value.message)); }
        catch (error) { setError(message(error)); } finally { setBusy(false); }
      }}>Uruchom oczekujące warianty</Button><Button variant="outline" disabled={busy} onClick={() => setAttempt(value => value + 1)}>Odśwież eksperyment</Button><Button disabled={busy || data.state !== "finished"} onClick={() => setShowComparison(true)}>Porównaj warianty</Button></div>
      {launchErrors.length > 0 && <div role="alert" className="mt-4 text-sm"><p>Część wariantów nie wystartowała. Oczekujące można ponowić przyciskiem uruchomienia.</p>{launchErrors.map(value => <p className="break-all" key={value}>{value}</p>)}</div>}
      <div className="mt-6 grid gap-4 sm:grid-cols-2">{data.sessions.map((session, index) => <section key={session.id} className="min-w-0 rounded-xl border bg-card p-5"><h3 className="font-semibold">Wariant {String.fromCharCode(65 + index)} · {statusLabels[session.status]}</h3><p className="mt-2 text-sm">{session.config.strategy.toUpperCase()} · {session.config.scope} · {session.config.link_types} · głębokość {session.config.max_depth}</p><p className="mt-2 text-sm">Pobrane HTML: {session.fetched_count} · linki: {session.link_count} · błędy: {session.error_count}</p><p className="mt-2 break-all text-xs">{session.stop_reason} · {session.id}</p><div className="mt-4 flex flex-wrap gap-3 text-sm"><Link className="text-teal-800 underline" to={"/sessions/" + session.id}>Sesja / anulowanie</Link><Link className="text-teal-800 underline" to={"/graph/" + session.id}>Graf</Link><Link className="text-teal-800 underline" to={"/data/" + session.id}>Dane</Link></div></section>)}</div>
      <div className="mt-6"><Button variant="outline" disabled={busy} onClick={() => setConfirmDelete(true)}>Usuń grupę eksperymentu</Button>{confirmDelete && <section className="mt-4 rounded-lg border border-red-200 bg-red-50 p-4" aria-label="Potwierdzenie usunięcia eksperymentu"><p className="text-sm">Usunąć grupę? Sesje i ich wyniki pozostaną; aktywne sesje nadal działają.</p><div className="mt-3 flex flex-wrap gap-3"><Button variant="destructive" disabled={busy} onClick={async () => { setBusy(true); try { await comparisonApi.remove(id); navigate("/experiments"); } catch (error) { setError(message(error)); setBusy(false); } }}>Potwierdź usunięcie grupy</Button><Button variant="outline" onClick={() => setConfirmDelete(false)}>Zachowaj grupę</Button></div></section>}</div>
      {showComparison && data.state === "finished" && <ComparisonResults key={data.sessions.map(item => item.id).join(",")} ids={data.sessions.map(item => item.id)} />}
    </>}
  </>;
}

export function ExperimentsPage() {
  const { id } = useParams();
  return <><p className="eyebrow">POWTARZALNE KONFIGURACJE I POMIARY</p><h1 className="mt-3 text-3xl font-semibold">Porównania i eksperymenty</h1><p className="mt-4 text-muted-foreground">Zmieniaj strategię, zakres, rodzaje linków i limity. Porównuj rzeczywiście zapisane zbiory i metadane.</p>
    {id ? <ExperimentDetail key={id} id={id} /> : <><ExperimentForm /><ExperimentList /><SavedSessionComparison /></>}</>;
}
