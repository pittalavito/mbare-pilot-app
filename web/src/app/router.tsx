import { Navigate, createBrowserRouter, useParams } from "react-router-dom";

import { Placeholder } from "../pages/Placeholder";
import { ProjectsPage } from "../pages/ProjectsPage";
import { Layout } from "./Layout";

function ProjectPage() {
  const { project = "" } = useParams();
  return <Placeholder title={project} />;
}

/** One URL per page: a project and its tab can be bookmarked and reloaded. */
export const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <Navigate to="/projects" replace /> },
      { path: "projects", element: <ProjectsPage /> },
      { path: "projects/:project/*", element: <ProjectPage /> },
      { path: "library", element: <Placeholder title="Libreria" /> },
      { path: "admin", element: <Placeholder title="Admin" /> },
      { path: "*", element: <Placeholder title="Pagina non trovata" /> },
    ],
  },
]);
