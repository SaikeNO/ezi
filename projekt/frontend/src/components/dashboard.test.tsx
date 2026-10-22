import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { Dashboard, type DashboardData } from "./dashboard";
import { request } from "@/lib/sessions-api";

vi.mock("@/lib/sessions-api", () => ({ request: vi.fn() }));
const empty: DashboardData = { sessions: 0, discovered_pages: 0, fetched_pages: 0,
  errored_pages: 0, links: 0, statuses: { queued: 0, running: 0, completed: 0, failed: 0, cancelled: 0 }, recent: [] };
const mount = () => render(<MemoryRouter><Dashboard /></MemoryRouter>);

describe("dashboard", () => {
  it("renders empty database and real refreshed counters", async () => {
    vi.mocked(request).mockResolvedValueOnce(empty).mockResolvedValueOnce({ ...empty, sessions: 2,
      fetched_pages: 42, statuses: { ...empty.statuses, completed: 2 } });
    mount();
    expect(await screen.findByText(/Brak sesji/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Odśwież dashboard" }));
    expect(await screen.findByText("42")).toBeInTheDocument();
    expect(screen.getByText("Zakończona: 2")).toBeInTheDocument();
  });
  it("shows network error then retries", async () => {
    vi.mocked(request).mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(empty);
    mount(); expect(await screen.findByRole("alert")).toHaveTextContent("offline");
    await userEvent.click(screen.getByRole("button", { name: "Odśwież dashboard" }));
    expect(await screen.findByText(/Brak sesji/)).toBeInTheDocument();
  });
  it("rejects invalid metrics instead of inventing zeroes", async () => {
    vi.mocked(request).mockResolvedValueOnce({ ...empty, fetched_pages: -1 });
    mount(); expect(await screen.findByRole("alert")).toHaveTextContent("Nieprawidłowa odpowiedź");
  });
  it("aborts pending request on unmount", () => {
    vi.mocked(request).mockReturnValue(new Promise(() => {}));
    const view = mount();
    const signal = vi.mocked(request).mock.lastCall?.[1]?.signal;
    view.unmount(); expect(signal?.aborted).toBe(true);
  });
});
