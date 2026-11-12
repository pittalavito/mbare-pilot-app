import { Route } from "react-router-dom";

import { ProjectZone } from "../pages/project/ProjectZone";
import { DataRedirect, SectionRedirect } from "../pages/project/redirects";
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
