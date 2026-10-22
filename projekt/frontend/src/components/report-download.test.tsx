import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ReportDownload } from "./report-download";
import { request } from "@/lib/sessions-api";

vi.mock("@/lib/sessions-api", () => ({ request: vi.fn() }));

describe("HTML report downloads", () => {
  it("downloads session HTML; revokes object URL", async () => {
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:report"), revokeObjectURL: vi.fn() }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    vi.mocked(request).mockResolvedValue(new Blob(["<h1>Report</h1>"], { type: "text/html" }));
    render(<ReportDownload sessionId="abc" />);
    await userEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(click).toHaveBeenCalledOnce());
    expect(request).toHaveBeenCalledWith("/api/sessions/abc/report", expect.any(Object), true, 35000);
    await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:report"), { timeout: 2000 });
    click.mockRestore();
  });
  it("shows server errors and permits retry; comparison IDs stay explicit", async () => {
    vi.mocked(request).mockRejectedValue(new Error("Wyniki za duże"));
    render(<ReportDownload sessionIds={["a", "b"]} />);
    await userEvent.click(screen.getByRole("button"));
    expect(await screen.findByRole("alert")).toHaveTextContent("Wyniki za duże");
    expect(request).toHaveBeenCalledWith("/api/reports/compare", expect.objectContaining({ method: "POST", body: '{"session_ids":["a","b"]}' }), true, 35000);
    expect(screen.getByRole("button")).toBeEnabled();
  });
  it("cancels pending report without saving file", async () => {
    vi.mocked(request).mockReturnValue(new Promise(() => {}));
    render(<ReportDownload sessionId="abc" />);
    await userEvent.click(screen.getByRole("button"));
    const signal = vi.mocked(request).mock.lastCall?.[1]?.signal;
    await userEvent.click(screen.getByRole("button", { name: "Anuluj raport" }));
    expect(signal?.aborted).toBe(true);
    expect(screen.getByRole("button", { name: "Pobierz raport sesji HTML" })).toBeEnabled();
  });
});
