import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { eventsUrl, sessionsApi } from "@/lib/sessions-api";
import type { CrawlSession } from "@/types/sessions";

const reasons: Record<string, string> = {
  frontier_exhausted:
    "Przetworzono wszystkie dostępne adresy w wybranym zakresie.",
  page_limit: "Osiągnięto limit prób pobrania stron.",
  time_limit: "Osiągnięto limit czasu sesji. Częściowe wyniki zachowane.",
  user_cancelled: "Sesja anulowana. Częściowe wyniki zachowane.",
  server_shutdown:
    "Przerwano przy wyłączaniu backendu. Częściowe wyniki zachowane.",
  interrupted: "Sesja przerwana przez restart backendu.",
  start_failed: "Nie udało się pobrać strony startowej.",
  internal_error: "Wewnętrzny błąd crawlera. Częściowe wyniki zachowane.",
  link_limit: "Osiągnięto limit odnośników. Częściowe wyniki zachowane.",
  discovery_limit:
    "Osiągnięto limit odkrytych adresów. Częściowe wyniki zachowane.",
  origin_limit: "Osiągnięto limit hostów. Częściowe wyniki zachowane.",
};

export function CrawlControls({
  session,
  onChange,
  disabled = false,
}: {
  session: CrawlSession;
  onChange: (value: CrawlSession) => void;
  disabled?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [connection, setConnection] = useState("");
  const change = useRef(onChange);
  change.current = onChange;
  const operation = useRef(false);
  const read = useRef<AbortController | null>(null);

  useEffect(() => {
    setConnection("");
    if (session.status !== "running") return;
    let closed = false;
    let scheduled: ReturnType<typeof setTimeout> | undefined;
    async function refresh() {
      if (closed || operation.current || read.current) return;
      const controller = new AbortController();
      read.current = controller;
      try {
        const latest = await sessionsApi.read(session.id, controller.signal);
        if (!closed && !controller.signal.aborted) {
          change.current(latest);
          setConnection("");
        }
      } catch {
        if (!closed && !controller.signal.aborted)
          setConnection("Brak połączenia z postępem. Ponawianie odczytu…");
      } finally {
        if (read.current === controller) read.current = null;
      }
    }
    const source =
      typeof EventSource !== "undefined"
        ? new EventSource(eventsUrl(session.id))
        : null;
    const kinds = [
      "progress",
      "page_discovered",
      "page_fetched",
      "page_failed",
      "completed",
      "cancelled",
      "failure",
    ];
    const received = (event: Event) => {
      if (["completed", "cancelled", "failure"].includes(event.type))
        source?.close();
      if (!scheduled)
        scheduled = setTimeout(() => {
          scheduled = undefined;
          void refresh();
        }, 100);
    };
    kinds.forEach((kind) => source?.addEventListener(kind, received));
    if (source)
      source.onerror = () => {
        if (!closed)
          setConnection(
            "Połączenie z postępem przerwane. Odczyt automatyczny pozostaje aktywny.",
          );
      };
    // REST polling also recovers from missed SSE messages and temporary disconnects.
    const poll = setInterval(() => {
      void refresh();
    }, 1000);
    void refresh();
    return () => {
      closed = true;
      clearInterval(poll);
      if (scheduled) clearTimeout(scheduled);
      source?.close();
      read.current?.abort();
      read.current = null;
    };
  }, [session.id, session.status]);

  async function act(action: "start" | "cancel") {
    operation.current = true;
    read.current?.abort();
    read.current = null;
    setBusy(true);
    setError("");
    try {
      change.current(await sessionsApi[action](session.id));
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : "Nie udało się wykonać operacji.",
      );
    } finally {
      operation.current = false;
      setBusy(false);
    }
  }

  return (
    <section
      className="mt-8 rounded-2xl border bg-card p-6 sm:p-8"
      aria-labelledby="crawl-heading"
    >
      <h2 id="crawl-heading" className="text-xl font-semibold">
        Przebieg pobierania
      </h2>
      <p className="mt-3 text-sm text-muted-foreground">
        BFS/DFS zachowuje kolejność dzięki sekwencyjnemu pobieraniu. Limit stron
        obejmuje także nieudane próby.
      </p>
      <dl className="mt-6 grid grid-cols-2 gap-5 lg:grid-cols-4">
        {(
          [
            ["Odkryte adresy stron", session.discovered_count],
            ["Pobrane HTML", session.fetched_count],
            ["Odnalezione odnośniki", session.link_count],
            ["Błędy stron", session.error_count],
          ] as const
        ).map(([label, value]) => (
          <div key={label}>
            <dt className="text-sm text-muted-foreground">{label}</dt>
            <dd className="mt-2 text-2xl font-semibold">{value}</dd>
          </div>
        ))}
      </dl>
      {session.stop_reason && (
        <p role="status" className="mt-6 rounded-lg bg-slate-50 p-4 text-sm">
          {reasons[session.stop_reason] || "Przetwarzanie zakończone."}
        </p>
      )}
      {connection && (
        <p role="status" className="mt-4 text-sm text-amber-800">
          {connection}
        </p>
      )}
      {error && (
        <p role="alert" className="mt-4 text-sm text-red-800">
          {error}
        </p>
      )}
      <div className="mt-6 flex flex-wrap gap-3">
        {session.status === "queued" && (
          <Button disabled={busy || disabled} onClick={() => void act("start")}>
            {busy ? "Przetwarzanie…" : "Uruchom crawler"}
          </Button>
        )}
        {(session.status === "queued" || session.status === "running") && (
          <Button
            variant="outline"
            disabled={busy || disabled}
            onClick={() => void act("cancel")}
          >
            {busy ? "Przetwarzanie…" : "Anuluj sesję"}
          </Button>
        )}
      </div>
    </section>
  );
}
