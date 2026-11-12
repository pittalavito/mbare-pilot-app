import { Navigate, useParams, useSearchParams } from "react-router-dom";

import { NOTE_PREFIXES } from "../../api/projectData";
import { WIP_NOTE } from "../../api/wip";

/** The links of the tabs of before the three zones (also written by the agents
 * in their answers and by the API: ``/projects/<p>/data?note=…``). */

const base = (project: string) => `/projects/${encodeURIComponent(project)}`;

/** Where a note lives now: activities, agent tasks and the WIP note in «Lavoro», the rest in «Progetto». */
export function noteZone(note: string | null): "work" | "project" {
  if (!note) return "work";
  return note === WIP_NOTE || note.startsWith(NOTE_PREFIXES.activity) || note.startsWith(NOTE_PREFIXES.agent_task) ? "work" : "project";
}

/** ``/data[?note=…]`` → the zone of the note (no note: «Lavoro»). */
export function DataRedirect() {
  const { project = "" } = useParams();
  const [search] = useSearchParams();
  const note = search.get("note");
  return <Navigate to={`${base(project)}/${noteZone(note)}${note ? `?note=${encodeURIComponent(note)}` : ""}`} replace />;
}

/** ``/git``, ``/atlassian``, ``/settings`` → that section of «Progetto». */
export function SectionRedirect({ section }: { section: string }) {
  const { project = "" } = useParams();
  return <Navigate to={`${base(project)}/project?tab=${section}`} replace />;
}
