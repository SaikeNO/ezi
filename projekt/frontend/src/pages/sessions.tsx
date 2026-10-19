import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { CrawlControls } from "@/components/crawl-controls";
import { SessionForm } from "@/components/session-form";
import { sessionsApi } from "@/lib/sessions-api";
import {
  statusLabels,
  type CrawlSession,
  type SessionList,
  type SessionStatus,
} from "@/types/sessions";

type Load<T> =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; data: T };
const errorText = (error: unknown) =>
  error instanceof Error ? error.message : "Nie udało się odczytać sesji.";
const date = (value: string) =>
  new Intl.DateTimeFormat("pl-PL", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));

export function SessionsPage() {
  const navigate = useNavigate();
  const [offset, setOffset] = useState(0);
  const [filter, setFilter] = useState<SessionStatus | "">("");
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<Load<SessionList>>({ kind: "loading" });
  useEffect(() => {
    const controller = new AbortController();
    setState({ kind: "loading" });
    sessionsApi.list(offset, filter, controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) setState({ kind: "ready", data });
      },
      (error) => {
        if (!controller.signal.aborted)
          setState({ kind: "error", message: errorText(error) });
      },
    );
    return () => controller.abort();
  }, [offset, filter, attempt]);
  return (
    <>
      <p className="eyebrow">ZAPISANE KONFIGURACJE</p>
      <h1 className="mt-3 text-3xl font-semibold">Sesje</h1>
      <p className="mt-4 text-muted-foreground">
        Utwórz sesję, uruchom crawler i przejrzyj graf zapisanych wyników.
      </p>
      <section
        className="mt-8 rounded-2xl border bg-card p-6 sm:p-8"
        aria-labelledby="new-session"
      >
        <h2 id="new-session" className="mb-6 text-xl font-semibold">
          Nowa sesja
        </h2>
        <SessionForm
          onSave={async (input) => {
            const saved = await sessionsApi.create(input);
            navigate(`/sessions/${saved.id}`);
          }}
        />
      </section>
      <section
        className="mt-8 rounded-2xl border bg-card p-6 sm:p-8"
        aria-labelledby="saved-sessions"
      >
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <h2 id="saved-sessions" className="text-xl font-semibold">
            Zapisane sesje
          </h2>
          <label className="text-sm">
            Filtr statusu
            <select
              value={filter}
              onChange={(event) => {
                setFilter(event.target.value as SessionStatus | "");
                setOffset(0);
              }}
              className="ml-3 rounded-lg border p-2"
            >
              <option value="">Wszystkie</option>
              {Object.entries(statusLabels).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>
        {state.kind === "loading" && <p role="status">Wczytywanie sesji…</p>}
        {state.kind === "error" && (
          <div role="alert">
            <p>{state.message}</p>
            <Button
              variant="outline"
              className="mt-4"
              onClick={() => setAttempt((value) => value + 1)}
            >
              Spróbuj ponownie
            </Button>
          </div>
        )}
        {state.kind === "ready" && (
          <>
            {state.data.items.length === 0 ? (
              <p className="text-muted-foreground">
                Brak zapisanych sesji dla wybranego filtra.
              </p>
            ) : (
              <ul className="divide-y">
                {state.data.items.map((item) => (
                  <li
                    key={item.id}
                    className="flex flex-wrap items-center justify-between gap-4 py-5"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="break-all font-medium">{item.start_url}</p>
                      <p className="mt-2 text-sm text-muted-foreground">
                        {statusLabels[item.status]} · {date(item.created_at)} ·{" "}
                        {item.config.strategy.toUpperCase()}, głębokość{" "}
                        {item.config.max_depth}
                      </p>
                    </div>
                    <Link
                      to={`/sessions/${item.id}`}
                      className="rounded-lg border px-4 py-2 text-sm font-medium text-teal-800 hover:bg-teal-50"
                    >
                      Szczegóły
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            <div className="mt-6 flex flex-wrap items-center gap-3">
              <Button
                variant="outline"
                disabled={offset === 0}
                onClick={() => setOffset((value) => Math.max(0, value - 10))}
              >
                Poprzednie
              </Button>
              <span className="text-sm text-muted-foreground">
                Łącznie: {state.data.total}
              </span>
              <Button
                variant="outline"
                disabled={offset + 10 >= state.data.total}
                onClick={() => setOffset((value) => value + 10)}
              >
                Następne
              </Button>
            </div>
          </>
        )}
      </section>
    </>
  );
}

const configLabels: Record<keyof CrawlSession["config"], string> = {
  strategy: "Strategia",
  scope: "Zakres",
  link_types: "Rodzaje linków",
  max_depth: "Maksymalna głębokość",
  max_pages: "Limit stron",
  timeout_seconds: "Limit żądania (s)",
  request_delay_ms: "Opóźnienie (ms)",
  max_duration_seconds: "Limit sesji (s)",
  max_response_bytes: "Limit odpowiedzi (bajty)",
  max_redirects: "Limit przekierowań",
  concurrency: "Współbieżność",
  respect_robots: "Respektuj robots.txt",
  follow_external_urls: "Podążaj za zewnętrznymi",
  process_one_page: "Tylko strona startowa",
};
const valueLabels: Record<string, string> = {
  bfs: "BFS (wszerz)",
  dfs: "DFS (w głąb)",
  server: "Ten sam host",
  web: "Sieć WWW",
  hyperlinks: "Hiperłącza",
  images_and_hyperlinks: "Obrazy i hiperłącza",
  all_links: "Wszystkie obsługiwane",
};

export function SessionDetail() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [state, setState] = useState<Load<CrawlSession>>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    setState({ kind: "loading" });
    setEditing(false);
    setConfirmDelete(false);
    setError("");
    sessionsApi.read(id, controller.signal).then(
      (data) => {
        if (!controller.signal.aborted) setState({ kind: "ready", data });
      },
      (error) => {
        if (!controller.signal.aborted)
          setState({ kind: "error", message: errorText(error) });
      },
    );
    return () => controller.abort();
  }, [id, attempt]);
  if (state.kind === "loading") return <p role="status">Wczytywanie sesji…</p>;
  if (state.kind === "error")
    return (
      <section>
        <h1 className="text-3xl font-semibold">Sesja niedostępna</h1>
        <p role="alert" className="my-5">
          {state.message}
        </p>
        <Button
          variant="outline"
          onClick={() => setAttempt((value) => value + 1)}
        >
          Spróbuj ponownie
        </Button>
        <Link className="ml-4 text-teal-800 underline" to="/sessions">
          Wróć do sesji
        </Link>
      </section>
    );
  const item = state.data;
  return (
    <>
      <Link to="/sessions" className="text-sm text-teal-800 underline">
        Wróć do sesji
      </Link>
      <p className="eyebrow mt-8">KONFIGURACJA ZAPISANA</p>
      <h1 className="mt-3 text-3xl font-semibold">Szczegóły sesji</h1>
      <p className="mt-5 break-all text-lg font-medium">{item.start_url}</p>
      <p className="mt-2 text-sm text-muted-foreground">
        {statusLabels[item.status]} · {date(item.created_at)}
      </p>
      <p className="mt-2 break-all text-xs text-muted-foreground">
        ID: {item.id}
      </p>
      <CrawlControls
        session={item}
        disabled={editing}
        onChange={(data) => setState({ kind: "ready", data })}
      />
      <Link to={"/graph/" + id} className="mt-6 inline-block rounded-lg border bg-white px-4 py-3 text-sm font-medium text-teal-800 hover:bg-teal-50">Otwórz graf sesji</Link>
      {item.error && (
        <p role="alert" className="mt-4 text-red-800">
          {item.error}
        </p>
      )}
      <section
        className="mt-8 rounded-2xl border bg-card p-6 sm:p-8"
        aria-labelledby="config-heading"
      >
        <h2 id="config-heading" className="mb-6 text-xl font-semibold">
          Parametry sesji
        </h2>
        {editing ? (
          <SessionForm
            initial={item}
            onSave={async (input) => {
              const saved = await sessionsApi.update(id, input);
              setState({ kind: "ready", data: saved });
              setEditing(false);
            }}
            onCancel={() => setEditing(false)}
          />
        ) : (
          <>
            <dl className="grid gap-5 sm:grid-cols-2">
              {Object.entries(item.config).map(([field, value]) => (
                <div key={field}>
                  <dt className="text-sm text-muted-foreground">
                    {configLabels[field as keyof typeof configLabels]}
                  </dt>
                  <dd className="mt-1 font-medium">
                    {typeof value === "boolean"
                      ? value
                        ? "Tak"
                        : "Nie"
                      : valueLabels[String(value)] || String(value)}
                  </dd>
                </div>
              ))}
            </dl>
            <div className="mt-8 flex flex-wrap gap-3">
              {item.status === "queued" && (
                <Button
                  variant="outline"
                  onClick={() => {
                    setEditing(true);
                    setConfirmDelete(false);
                  }}
                >
                  Edytuj konfigurację
                </Button>
              )}
              <Button
                variant="outline"
                disabled={item.status === "running"}
                onClick={() => setConfirmDelete(true)}
              >
                Usuń sesję
              </Button>
            </div>
          </>
        )}
        {confirmDelete && (
          <section
            aria-label="Potwierdzenie usunięcia"
            className="mt-6 rounded-lg border border-red-200 bg-red-50 p-5"
          >
            <p className="mb-4 text-sm text-red-900">
              Usunąć tę sesję i wszystkie jej zapisane wyniki?
            </p>
            <div className="flex flex-wrap gap-3">
              <Button
                variant="destructive"
                disabled={deleting}
                onClick={async () => {
                  setDeleting(true);
                  setError("");
                  try {
                    await sessionsApi.remove(id);
                    navigate("/sessions");
                  } catch (error) {
                    setError(errorText(error));
                    setDeleting(false);
                  }
                }}
              >
                {deleting ? "Usuwanie…" : "Potwierdź usunięcie"}
              </Button>
              <Button
                variant="outline"
                disabled={deleting}
                onClick={() => setConfirmDelete(false)}
              >
                Zachowaj sesję
              </Button>
            </div>
          </section>
        )}
        {error && (
          <p role="alert" className="mt-4 text-red-800">
            {error}
          </p>
        )}
      </section>
    </>
  );
}
