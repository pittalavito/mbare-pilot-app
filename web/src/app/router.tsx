import { Navigate, createBrowserRouter } from "react-router-dom";

import { Placeholder } from "../pages/Placeholder";
import { AdminPage } from "../pages/admin/AdminPage";
import { AutomationTab } from "../pages/automation/AutomationTab";
import { LibraryPage } from "../pages/library/LibraryPage";
import { ProjectPage } from "../pages/project/ProjectPage";
import { ProjectZone } from "../pages/project/ProjectZone";
import { CopilotRedirect, DataRedirect, SectionRedirect } from "../pages/project/redirects";
import { ProjectsPage } from "../pages/projects/ProjectsPage";
import { WorkZone } from "../pages/work/WorkZone";
import { Layout } from "./Layout";

/** The graph editor (React Flow) is a chunk of its own, downloaded when opened. */
const automationEditor = () => import("../pages/automation/AutomationEditor").then((module) => ({ Component: module.AutomationEditor }));

/** A project's tabs: each is a route, loaded only when open. */
const PROJECT_TABS = [
  { path: "work", element: <WorkZone /> },
  { path: "automation", element: <AutomationTab /> },
  { path: "automation/new", lazy: automationEditor },
  { path: "automation/:pipelineId/edit", lazy: automationEditor },
  { path: "project", element: <ProjectZone /> },
  // The tabs of before: their links (also the ones the agents and the API write) open the new place.
  { path: "chat", element: <Navigate to="../work" replace /> },
  { path: "copilot", element: <CopilotRedirect /> },
  { path: "data", element: <DataRedirect /> },
  { path: "git", element: <SectionRedirect section="git" /> },
  { path: "atlassian", element: <SectionRedirect section="atlassian" /> },
  { path: "settings", element: <SectionRedirect section="settings" /> },
];

/** One URL per page: a project and its tab can be bookmarked and reloaded. */
export const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <Navigate to="/projects" replace /> },
      { path: "projects", element: <ProjectsPage /> },
      { path: "projects/:project", element: <ProjectPage />, children: PROJECT_TABS },
      { path: "library", element: <LibraryPage /> },
      { path: "admin", element: <AdminPage /> },
      { path: "*", element: <Placeholder title="Pagina non trovata" /> },
    ],
  },
]);
