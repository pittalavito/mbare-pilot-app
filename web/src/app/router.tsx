import { Navigate, createBrowserRouter } from "react-router-dom";

import { Placeholder } from "../pages/Placeholder";
import { AutomationTab } from "../pages/automation/AutomationTab";
import { ChatTab } from "../pages/chat/ChatTab";
import { ProjectPage } from "../pages/project/ProjectPage";
import { ProjectsPage } from "../pages/projects/ProjectsPage";
import { Layout } from "./Layout";

/** The graph editor (React Flow) is a chunk of its own, downloaded when opened. */
const automationEditor = () => import("../pages/automation/AutomationEditor").then((module) => ({ Component: module.AutomationEditor }));

/** A project's tabs: each is a route, loaded only when open. */
const PROJECT_TABS = [
  { path: "chat", element: <ChatTab /> },
  { path: "automation", element: <AutomationTab /> },
  { path: "automation/new", lazy: automationEditor },
  { path: "automation/:pipelineId/edit", lazy: automationEditor },
  { path: "data", element: <Placeholder title="Dati" /> },
  { path: "git", element: <Placeholder title="Git" /> },
  { path: "atlassian", element: <Placeholder title="Atlassian" /> },
  { path: "settings", element: <Placeholder title="Impostazioni" /> },
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
      { path: "library", element: <Placeholder title="Libreria" /> },
      { path: "admin", element: <Placeholder title="Admin" /> },
      { path: "*", element: <Placeholder title="Pagina non trovata" /> },
    ],
  },
]);
