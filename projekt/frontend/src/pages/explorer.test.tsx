import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ExplorerPage } from "./explorer";
import { explorerApi, saveCsv } from "@/lib/explorer-api";

vi.mock("@/lib/explorer-api", async importOriginal => ({ ...await importOriginal<typeof import("@/lib/explorer-api")>(), saveCsv: vi.fn() }));
const row = { id: "p", normalized_url: "https://example.com/", title: "<b>Łódź</b>", description: null,
  keywords: "=1+1", depth: 0, final_url: "https://example.com/", http_status: 200, error: null };
const list = { items: [row], total: 13, offset: 0, limit: 10 };
const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });
function mount(path = "/data/s") {
  return render(<MemoryRouter initialEntries={[path]}><Routes><Route path="/data/:id?" element={<ExplorerPage />} /></Routes></MemoryRouter>);
}

describe("data explorer", () => {
  it("applies server filters, resets pagination and renders literal metadata", async () => {
    const fetcher = vi.fn().mockImplementation(() => Promise.resolve(response(list)));
    vi.stubGlobal("fetch", fetcher); mount();
    expect(await screen.findByText("<b>Łódź</b>")).toBeInTheDocument();
    expect(document.querySelector("tbody b")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Następne strony" }));
    await waitFor(() => expect(fetcher).toHaveBeenLastCalledWith(expect.stringContaining("offset=10"), expect.any(Object)));
    await screen.findByText("<b>Łódź</b>");
    await userEvent.type(screen.getByRole("textbox", { name: "Szukaj w URL i metadanych" }), "żółć");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Pobrany HTML" }), "true");
    await userEvent.click(screen.getByRole("button", { name: "Zastosuj filtry" }));
    await waitFor(() => expect(fetcher).toHaveBeenLastCalledWith(expect.stringContaining("offset=0"), expect.any(Object)));
    const url = String(fetcher.mock.lastCall![0]);
    expect(url).toContain("fetched=true"); expect(url).toContain("q=%C5%BC%C3%B3%C5%82%C4%87");
  });

  it("exports selected order, separator and BOM using applied filters", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.resolve(response(list))));
    const csv = vi.spyOn(explorerApi, "csv").mockResolvedValue(new Blob(["URL;Keyword\r\n"]));
    mount(); await screen.findByText("<b>Łódź</b>");
    await userEvent.click(screen.getByRole("checkbox", { name: "URL" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Title" }));
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Separator" }), "semicolon");
    await userEvent.click(screen.getByRole("checkbox", { name: "UTF-8 z BOM" }));
    await userEvent.type(screen.getByRole("textbox"), "unapplied");
    await userEvent.click(screen.getByRole("button", { name: "Pobierz CSV" }));
    await screen.findByText("Plik CSV przekazany do pobrania.");
    expect(csv).toHaveBeenCalledWith("s", expect.objectContaining({ q: "" }), ["keywords", "title"], "semicolon", false, expect.any(AbortSignal));
    expect(saveCsv).toHaveBeenCalled();
    await userEvent.click(screen.getByRole("checkbox", { name: "Keyword" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Title" }));
    expect(screen.getByRole("button", { name: "Pobierz CSV" })).toBeDisabled();
  });

  it("download errors stay visible and can be retried", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.resolve(response(list))));
    vi.spyOn(explorerApi, "csv").mockRejectedValueOnce(new Error("Eksport za duży")).mockResolvedValue(new Blob(["csv"]));
    mount(); await screen.findByText("<b>Łódź</b>");
    await userEvent.click(screen.getByRole("button", { name: "Pobierz CSV" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Eksport za duży");
    await userEvent.click(screen.getByRole("button", { name: "Pobierz CSV" }));
    expect(await screen.findByText("Plik CSV przekazany do pobrania.")).toBeInTheDocument();
  });

  it("aborts download when leaving page", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.resolve(response(list))));
    let signal: AbortSignal | undefined;
    vi.spyOn(explorerApi, "csv").mockImplementation((_id, _filters, _fields, _separator, _bom, cancellation) => {
      signal = cancellation; return new Promise(() => {});
    });
    const view = mount(); await screen.findByText("<b>Łódź</b>");
    await userEvent.click(screen.getByRole("button", { name: "Pobierz CSV" }));
    view.unmount(); expect(signal?.aborted).toBe(true);
  });

  it("empty data and retry are honest", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue(response({ ...list, items: [], total: 0 })));
    mount(); await screen.findByRole("alert");
    await userEvent.click(screen.getByRole("button", { name: "Odśwież dane" }));
    expect(await screen.findByText("Brak stron dla wybranych filtrów.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Następne strony" })).toBeDisabled();
  });
});
