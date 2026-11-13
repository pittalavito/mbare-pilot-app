import { Navigate, Route } from "react-router-dom";

import { ProjectZone } from "../pages/project/ProjectZone";
import { AutomationTab } from "../pages/automation/AutomationTab";
import { ProjectPage } from "../pages/project/ProjectPage";
import { CopilotRedirect, DataRedirect, SectionRedirect } from "../pages/project/redirects";
import { WorkZone } from "../pages/work/WorkZone";

/** The zones «Lavoro» and «Progetto» as the router mounts them, with the
 * redirects of the old tabs: put it inside a test's ``<Routes>``. A test can
 * start from ``/projects/acme/data?note=…`` (as a link written by an agent) and
 * lands in the right zone. */
export function zoneRoutes() {
  return (
    <>
      <Route path="/projects/:project/work" element={<WorkZone />} />
      <Route path="/projects/:project/project" element={<ProjectZone />} />
      <Route path="/projects/:project/data" element={<DataRedirect />} />
      <Route path="/projects/:project/git" element={<SectionRedirect section="git" />} />
      <Route path="/projects/:project/settings" element={<SectionRedirect section="settings" />} />
    </>
  );
}

/** The whole project page (header, zones, agent panel), as the router mounts it. */
export function projectRoutes() {
  return (
    <Route path="/projects/:project" element={<ProjectPage />}>
      <Route path="work" element={<WorkZone />} />
      <Route path="project" element={<ProjectZone />} />
      <Route path="automation" element={<AutomationTab />} />
      <Route path="data" element={<DataRedirect />} />
      <Route path="chat" element={<Navigate to="../work" replace />} />
      <Route path="copilot" element={<CopilotRedirect />} />
    </Route>
  );
}

/** What the project page reads besides the open zone: the project, «Oggi», the
 * notes, the agents and Copilot's sessions (all empty: a test adds its own). */
export const PROJECT_API = {
  "GET /projects/acme": {
    name: "acme", description: "", source: "folder", root_path: "/code/acme", embedding_model: "", created_at: "2026-11-13T10:00:00Z", folder_exists: true,
  },
  "GET /projects/acme/today": { date: "2026-11-13", due_soon_days: 3, waiting: [], overdue: [], due_soon: [], to_close: [] },
  "GET /projects/acme/activities": [],
  "GET /projects/acme/agent-tasks": [],
  "GET /projects/acme/notes": [],
  "GET /projects/acme/chatbots": [],
  "GET /projects/acme/copilot-sessions": [],
  "GET /projects/acme/references": [],
  "GET /projects/acme/wip": { content: "", pending_words: 0 },
  "GET /projects/acme/pipelines": [],
};
