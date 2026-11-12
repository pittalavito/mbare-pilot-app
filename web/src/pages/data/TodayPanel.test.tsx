import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mockApi, renderPage } from "../../test/render";
import { zoneRoutes } from "../../test/zones";
import { addDays } from "./TodayPanel";

afterEach(() => { vi.unstubAllGlobals(); window.localStorage.clear(); });

const ACTIVITY = {
  name: "attivita-rilascio.md", title: "Rilascio", status: "in_progress", description: "", learned: "",
  items: [{ text: "Note", done: false, priority: null, due: "2026-11-08" }, { text: "Tag", done: false, priority: null, due: "2026-11-12" }],
  agent_tasks: [], references: [],
};
const FINISHED = { ...ACTIVITY, name: "attivita-finita.md", title: "Finita", items: [{ text: "a", done: true, priority: null, due: null }] };
const TASK = { name: "agent-task-nuovo.md", title: "Nuovo", status: "created", type: "development", objective: "", context: "", criteria: [], constraints: "", references: [] };
const item = (text: string, number: number, due: string) => ({ activity: ACTIVITY.name, activity_title: "Rilascio", item: number, text, due });
const TODAY = {
  date: "2026-11-10", due_soon_days: 3,
  waiting: [
    { kind: "task", task: TASK.name, title: "Nuovo", status: "created", session_id: null },
    { kind: "copilot", task: "agent-task-pronto.md", title: "Pronto", status: "question", session_id: 7 },
  ],
  overdue: [item("Note", 1, "2026-11-08")],
  due_soon: [item("Tag", 2, "2026-11-12")],
  to_close: [{ activity: FINISHED.name, title: "Finita", items: 1 }],
};

function api(today: unknown = TODAY) {
  const bodies: unknown[] = [];
  const checked = vi.fn(async (request: Request) => { bodies.push(await request.json()); return new Response(null, { status: 204 }); });
  const postponed = vi.fn(async (request: Request) => { await request.json(); return new Response(null, { status: 204 }); });
  const saved = vi.fn(async (request: Request) => ({ ...FINISHED, ...(await request.json()) }));
  const fetchMock = mockApi({
    "GET /projects/acme/notes": [],
    "GET /projects/acme/today": today,
    "GET /projects/acme/activities": [ACTIVITY, FINISHED],
    "GET /projects/acme/agent-tasks": [TASK],
    "GET /projects/acme/copilot-sessions": [],
    "GET /projects/acme/chatbots": [],
    "POST /projects/acme/activities/attivita-rilascio.md/items/1/check": checked,
    "POST /projects/acme/activities/attivita-rilascio.md/items/2/due": postponed,
    "PUT /projects/acme/activities/attivita-finita.md": saved,
  });
  return { checked, postponed, saved, fetchMock, bodies };
}

async function renderActivities() {
  renderPage(<Routes>{zoneRoutes()}</Routes>, { route: "/projects/acme/data" });
  fireEvent.click(await screen.findByRole("tab", { name: /Attività/ }));
}

const todayCalls = (fetchMock: ReturnType<typeof mockApi>) =>
  fetchMock.mock.calls.filter(([request]) => (request as Request).method === "GET" && (request as Request).url.endsWith("/today")).length;

describe("📌 Oggi", () => {
  it("shows the sections in order, each item linked", async () => {
    api();
    await renderActivities();

    const titles = await screen.findAllByText(/Aspettano te|Scadute|In scadenza|Da chiudere/);
    expect(titles.map((title) => title.textContent?.replace(/\d+$/, "").trim())).toEqual([
      "⏳ Aspettano te", "🔴 Scadute", "🟠 In scadenza (3 giorni)", "✅ Da chiudere",
    ]);
    expect(screen.getByText("Copilot ti fa una domanda")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Pronto/ })).toHaveAttribute("href", "/projects/acme/copilot?session=7");

    fireEvent.click(screen.getByRole("button", { name: "Nuovo" })); // the task opens in its tab
    expect(await screen.findByRole("tab", { name: /Tutti i task/, selected: true })).toBeInTheDocument();
  });

  it("checks an item and refreshes", async () => {
    const { checked, fetchMock, bodies } = api();
    await renderActivities();
    const before = todayCalls(fetchMock);

    fireEvent.click(await screen.findByRole("button", { name: "Spunta Note" }));

    await waitFor(() => expect(checked).toHaveBeenCalled());
    expect(bodies).toEqual([{ text: "Note" }]);
    await waitFor(() => expect(todayCalls(fetchMock)).toBeGreaterThan(before));
  });

  it("postpones an item by a week from its date, or to a chosen date", async () => {
    const { postponed } = api();
    await renderActivities();

    fireEvent.click(await screen.findByRole("button", { name: "Rimanda Tag" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "+1 settimana" }));
    await waitFor(() => expect(postponed).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByRole("button", { name: "Rimanda Tag" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: /Scegli la data/ }));
    fireEvent.change(await screen.findByLabelText("Nuova scadenza"), { target: { value: "2026-12-01" } });
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Rimanda" }));
    await waitFor(() => expect(postponed).toHaveBeenCalledTimes(2));
  });

  it("closes an activity with «Imparato»", async () => {
    const { saved } = api();
    await renderActivities();

    fireEvent.click(await screen.findByRole("button", { name: "Segna fatta" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/Imparato/), { target: { value: "Il tag dopo le note" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Segna fatta" }));

    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(await saved.mock.results[0].value).toMatchObject({ status: "done", learned: "Il tag dopo le note" });
  });

  it("collapses, remembering it, and says when there is nothing", async () => {
    api({ ...TODAY, waiting: [], overdue: [], due_soon: [], to_close: [] });
    await renderActivities();

    expect(await screen.findByText(/Niente che ti aspetta/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Oggi/ }));
    expect(window.localStorage.getItem("mbare-pilot.today-collapsed.acme")).toBe("1");
  });

  it("adds days across months", () => {
    expect(addDays("2026-11-28", 7)).toBe("2026-12-05");
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
  });
});
