import { Navigate, createBrowserRouter } from "react-router-dom";

import { Placeholder } from "../pages/Placeholder";
import { AdminPage } from "../pages/admin/AdminPage";
import { AutomationTab } from "../pages/automation/AutomationTab";
import { AtlassianTab } from "../pages/atlassian/AtlassianTab";
import { ChatTab } from "../pages/chat/ChatTab";
import { LibraryPage } from "../pages/library/LibraryPage";
import { DataTab } from "../pages/data/DataTab";
import { GitTab } from "../pages/git/GitTab";
import { ProjectPage } from "../pages/project/ProjectPage";
import { ProjectsPage } from "../pages/projects/ProjectsPage";
import { SettingsTab } from "../pages/settings/SettingsTab";
import { Layout } from "./Layout";

/** The graph editor (React Flow) is a chunk of its own, downloaded when opened. */
const automationEditor = () => import("../pages/automation/AutomationEditor").then((module) => ({ Component: module.AutomationEditor }));

/** A project's tabs: each is a route, loaded only when open. */
const PROJECT_TABS = [
  { path: "chat", element: <ChatTab /> },
  { path: "automation", element: <AutomationTab /> },
  { path: "automation/new", lazy: automationEditor },
  { path: "automation/:pipelineId/edit", lazy: automationEditor },
  { path: "data", element: <DataTab /> },
  { path: "git", element: <GitTab /> },
  { path: "atlassian", element: <AtlassianTab /> },
  { path: "settings", element: <SettingsTab /> },
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
