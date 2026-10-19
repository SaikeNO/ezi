import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/sessions-api";
import {
  defaultConfig,
  type CrawlConfig,
  type SessionInput,
} from "@/types/sessions";

const inputClass =
  "mt-2 w-full rounded-lg border bg-white px-3 py-2 text-sm focus:outline-teal-700";
const numberFields = [
  ["max_depth", "Maksymalna głębokość", 0, 20, 1],
  ["max_pages", "Limit stron", 1, 10000, 1],
  ["timeout_seconds", "Limit czasu żądania (s)", 1, 60, 0.1],
  ["request_delay_ms", "Opóźnienie żądań (ms)", 100, 60000, 1],
  ["max_duration_seconds", "Limit czasu sesji (s)", 1, 3600, 1],
  ["max_response_bytes", "Limit odpowiedzi (bajty)", 1024, 10485760, 1],
  ["max_redirects", "Limit przekierowań", 0, 10, 1],
  ["concurrency", "Współbieżność", 1, 8, 1],
] as const;

const fieldLabels: Record<string, string> = {
  start_url: "Adres startowy", config: "Parametry sesji",
  "config.strategy": "Strategia", "config.scope": "Zakres", "config.link_types": "Rodzaje linków",
  "config.respect_robots": "Respektuj robots.txt",
  "config.follow_external_urls": "Podążaj za linkami zewnętrznymi",
  "config.process_one_page": "Przetwórz tylko stronę startową",
  ...Object.fromEntries(numberFields.map(([field, label]) => [`config.${field}`, label])),
};

export function SessionForm({
  initial,
  onSave,
  onCancel,
}: {
  initial?: SessionInput;
  onSave: (input: SessionInput) => Promise<void>;
  onCancel?: () => void;
}) {
  const prefix = useId();
  const [input, setInput] = useState<SessionInput>(() =>
    initial
      ? { start_url: initial.start_url, config: { ...initial.config } }
      : { start_url: "", config: { ...defaultConfig } },
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{
    message: string;
    fields: string[];
  } | null>(null);
  function config<K extends keyof CrawlConfig>(
    field: K,
    value: CrawlConfig[K],
  ) {
    setInput((current) => ({
      ...current,
      config: { ...current.config, [field]: value },
    }));
  }
  return (
    <form
      onSubmit={async (event) => {
        event.preventDefault();
        setError(null);
        setBusy(true);
        try {
          await onSave(input);
        } catch (error) {
          setError({
            message:
              error instanceof Error
                ? error.message
                : "Nie udało się zapisać sesji.",
            fields: error instanceof ApiError ? error.fields : [],
          });
        } finally {
          setBusy(false);
        }
      }}
      className="space-y-6"
    >
      {error && (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800"
        >
          <p>{error.message}</p>
          {error.fields.length > 0 && (
            <p className="mt-2">Sprawdź pola: {error.fields.map(field => fieldLabels[field] || "Parametry sesji").join(", ")}.</p>
          )}
        </div>
      )}
      <fieldset disabled={busy} className="space-y-6 disabled:opacity-60">
        <label className="block text-sm font-medium" htmlFor={`${prefix}-url`}>
          Adres startowy
          <input
            id={`${prefix}-url`}
            type="url"
            required
            maxLength={2048}
            value={input.start_url}
            placeholder="https://example.com"
            onChange={(event) =>
              setInput((current) => ({
                ...current,
                start_url: event.target.value,
              }))
            }
            className={inputClass}
          />
        </label>
        <p className="text-sm text-muted-foreground">
          Zapis konfiguracji nie uruchamia pobierania stron. Strona startowa ma
          głębokość 0.
        </p>
        <div className="grid gap-5 sm:grid-cols-3">
          <label className="text-sm font-medium">
            Strategia
            <select
              className={inputClass}
              value={input.config.strategy}
              onChange={(event) =>
                config(
                  "strategy",
                  event.target.value as CrawlConfig["strategy"],
                )
              }
            >
              <option value="bfs">BFS (wszerz)</option>
              <option value="dfs">DFS (w głąb)</option>
            </select>
          </label>
          <label className="text-sm font-medium">
            Zakres
            <select
              className={inputClass}
              value={input.config.scope}
              onChange={(event) =>
                config("scope", event.target.value as CrawlConfig["scope"])
              }
            >
              <option value="server">Ten sam host (server)</option>
              <option value="web">Sieć WWW (web)</option>
            </select>
          </label>
          <label className="text-sm font-medium">
            Rodzaje linków
            <select
              className={inputClass}
              value={input.config.link_types}
              onChange={(event) =>
                config(
                  "link_types",
                  event.target.value as CrawlConfig["link_types"],
                )
              }
            >
              <option value="hyperlinks">Hiperłącza</option>
              <option value="images_and_hyperlinks">Obrazy i hiperłącza</option>
              <option value="all_links">Wszystkie obsługiwane</option>
            </select>
          </label>
        </div>
        <div className="grid gap-5 sm:grid-cols-2">
          {numberFields.slice(0, 2).map(([field, label, min, max, step]) => (
            <label key={field} className="text-sm font-medium">
              {label}
              <input
                className={inputClass}
                type="number"
                min={min}
                max={max}
                step={step}
                required
                value={Number.isNaN(input.config[field]) ? "" : input.config[field]}
                onChange={(event) => config(field, event.target.valueAsNumber)}
              />
            </label>
          ))}
        </div>
        <details className="rounded-lg border p-4">
          <summary className="cursor-pointer text-sm font-medium">
            Limity i ustawienia dodatkowe
          </summary>
          <div className="mt-5 grid gap-5 sm:grid-cols-2">
            {numberFields.slice(2).map(([field, label, min, max, step]) => (
              <label key={field} className="text-sm font-medium">
                {label}
                <input
                  className={inputClass}
                  type="number"
                  min={min}
                  max={max}
                  step={step}
                  required
                  value={Number.isNaN(input.config[field]) ? "" : input.config[field]}
                  onChange={(event) =>
                    config(field, event.target.valueAsNumber)
                  }
                />
              </label>
            ))}
          </div>
          <div className="mt-6 space-y-4">
            {(
              [
                ["respect_robots", "Respektuj robots.txt"],
                [
                  "follow_external_urls",
                  "Podążaj za linkami zewnętrznymi (tylko zakres web)",
                ],
                ["process_one_page", "Przetwórz tylko stronę startową"],
              ] as const
            ).map(([field, label]) => (
              <label key={field} className="flex items-center gap-3 text-sm">
                <input
                  type="checkbox"
                  checked={input.config[field]}
                  onChange={(event) => config(field, event.target.checked)}
                  className="h-4 w-4 accent-teal-700"
                />
                {label}
              </label>
            ))}
          </div>
        </details>
      </fieldset>
      <div className="flex flex-wrap gap-3">
        <Button type="submit" disabled={busy}>
          {busy ? "Zapisywanie…" : initial ? "Zapisz zmiany" : "Utwórz sesję"}
        </Button>
        {onCancel && (
          <Button
            type="button"
            variant="outline"
            disabled={busy}
            onClick={onCancel}
          >
            Anuluj edycję
          </Button>
        )}
      </div>
    </form>
  );
}
