import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { SessionDetail, SessionsPage } from "./sessions";
import { defaultConfig, type CrawlSession } from "@/types/sessions";

const saved: CrawlSession = {
  id: "cc845acb-f51f-4c57-9cb1-10707e83c635",
  start_url: "https://example.com/",
  status: "queued",
  created_at: "2026-10-19T08:00:00Z",
  started_at: null,
  finished_at: null,
  discovered_count: 0,
  fetched_count: 0,
  error_count: 0,
  error: null,
  link_count: 0, stop_reason: null, crawler_version: null, user_agent: null,
  config: { ...defaultConfig, strategy: "dfs", max_depth: 2 },
};
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status });
const list = (items: CrawlSession[] = []) => ({
  items,
  total: items.length,
  limit: 10,
  offset: 0,
});
function mount(path = "/sessions") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/sessions" element={<SessionsPage />} />
        <Route path="/sessions/:id" element={<SessionDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("sessions UI", () => {
  it("shows empty list, creates session and reads persisted config", async () => {
    const fetchMock = vi.fn((_url: string, options: RequestInit) =>
      Promise.resolve(
        options.method === "POST"
          ? json(saved, 201)
          : _url.includes(saved.id)
            ? json(saved)
            : json(list()),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    mount();
    expect(
      await screen.findByText("Brak zapisanych sesji dla wybranego filtra."),
    ).toBeInTheDocument();
    await userEvent.type(
      screen.getByLabelText("Adres startowy"),
      saved.start_url,
    );
    await userEvent.selectOptions(screen.getByLabelText("Strategia"), "dfs");
    await userEvent.clear(screen.getByLabelText("Maksymalna głębokość"));
    await userEvent.type(screen.getByLabelText("Maksymalna głębokość"), "2");
    await userEvent.click(screen.getByRole("button", { name: "Utwórz sesję" }));
    expect(
      await screen.findByRole("heading", { name: "Szczegóły sesji" }),
    ).toBeInTheDocument();
    expect(screen.getByText("DFS (w głąb)")).toBeInTheDocument();
    const posted = fetchMock.mock.calls.find(
      ([, options]) => options.method === "POST",
    );
    expect(JSON.parse(posted![1].body as string)).toMatchObject({
      start_url: saved.start_url,
      config: { strategy: "dfs", max_depth: 2, respect_robots: true },
    });
  });

  it("edits stored config and displays returned state", async () => {
    const updated = { ...saved, config: { ...saved.config, max_pages: 42 } };
    const fetchMock = vi.fn((_url: string, options: RequestInit) =>
      Promise.resolve(json(options.method === "PATCH" ? updated : saved)),
    );
    vi.stubGlobal("fetch", fetchMock);
    mount(`/sessions/${saved.id}`);
    await userEvent.click(
      await screen.findByRole("button", { name: "Edytuj konfigurację" }),
    );
    expect(screen.getByLabelText("Maksymalna głębokość")).toHaveValue(2);
    const input = screen.getByLabelText("Limit stron");
    await userEvent.clear(input);
    await userEvent.type(input, "42");
    await userEvent.click(
      screen.getByRole("button", { name: "Zapisz zmiany" }),
    );
    expect(
      await screen.findByText("42", { selector: "dd" }),
    ).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([, options]) => options.method === "PATCH"),
    ).toBe(true);
  });

  it("requires explicit delete, then returns to list", async () => {
    const fetchMock = vi.fn((_url: string, options: RequestInit) =>
      Promise.resolve(
        options.method === "DELETE"
          ? new Response(null, { status: 204 })
          : _url.includes(saved.id)
            ? json(saved)
            : json(list()),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    mount(`/sessions/${saved.id}`);
    await userEvent.click(
      await screen.findByRole("button", { name: "Usuń sesję" }),
    );
    expect(
      fetchMock.mock.calls.some(([, options]) => options.method === "DELETE"),
    ).toBe(false);
    await userEvent.click(
      screen.getByRole("button", { name: "Zachowaj sesję" }),
    );
    expect(
      screen.queryByRole("button", { name: "Potwierdź usunięcie" }),
    ).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Usuń sesję" }));
    await userEvent.click(
      screen.getByRole("button", { name: "Potwierdź usunięcie" }),
    );
    expect(
      await screen.findByRole("heading", { name: "Nowa sesja" }),
    ).toBeInTheDocument();
  });

  it("shows validation error and retains form data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, options: RequestInit) =>
        Promise.resolve(
          options.method === "POST"
            ? json(
                {
                  code: "validation_error",
                  message: "Nieprawidłowe parametry żądania",
                  details: [
                    {
                      location: ["body", "start_url"],
                      message: "invalid",
                      type: "value_error",
                    },
                  ],
                },
                422,
              )
            : json(list()),
        ),
      ),
    );
    mount();
    await userEvent.type(
      screen.getByLabelText("Adres startowy"),
      "http://localhost",
    );
    await userEvent.click(screen.getByRole("button", { name: "Utwórz sesję" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Sprawdź pola: Adres startowy",
    );
    expect(screen.getByLabelText("Adres startowy")).toHaveValue(
      "http://localhost",
    );
    expect(screen.getByRole("button", { name: "Utwórz sesję" })).toBeEnabled();
  });

  it("retries list fetch and filters by actual status", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("offline"))
      .mockResolvedValue(json(list([saved])));
    vi.stubGlobal("fetch", fetchMock);
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Brak połączenia",
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Spróbuj ponownie" }),
    );
    expect(await screen.findByText(saved.start_url)).toBeInTheDocument();
    await userEvent.selectOptions(
      screen.getByLabelText("Filtr statusu"),
      "queued",
    );
    await waitFor(() =>
      expect(fetchMock).toHaveBeenLastCalledWith(
        expect.stringContaining("status=queued"),
        expect.any(Object),
      ),
    );
  });

  it("disables deleting running sessions and hides editing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(json({ ...saved, status: "running" })),
    );
    mount(`/sessions/${saved.id}`);
    expect(
      await screen.findByRole("button", { name: "Usuń sesję" }),
    ).toBeDisabled();
    expect(
      screen.queryByRole("button", { name: "Edytuj konfigurację" }),
    ).not.toBeInTheDocument();
  });

  it("shows missing session and safe untrusted text", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          json(
            {
              code: "session_not_found",
              message: "<script>not executed</script>",
            },
            404,
          ),
        ),
    );
    const { container } = mount(`/sessions/${saved.id}`);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "<script>not executed</script>",
    );
    expect(container.querySelector("script")).toBeNull();
  });

  it("keeps session visible after delete conflict", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, options: RequestInit) =>
        Promise.resolve(
          options.method === "DELETE"
            ? json(
                {
                  code: "session_running",
                  message: "Nie można usunąć uruchomionej sesji",
                },
                409,
              )
            : json(saved),
        ),
      ),
    );
    mount(`/sessions/${saved.id}`);
    await userEvent.click(
      await screen.findByRole("button", { name: "Usuń sesję" }),
    );
    const confirmation = screen.getByRole("region", {
      name: "Potwierdzenie usunięcia",
    });
    await userEvent.click(
      within(confirmation).getByRole("button", { name: "Potwierdź usunięcie" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Nie można usunąć",
    );
    expect(
      screen.getByRole("heading", { name: "Szczegóły sesji" }),
    ).toBeInTheDocument();
  });
});
