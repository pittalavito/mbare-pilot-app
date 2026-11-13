import { Loader, Tabs } from "@mantine/core";
import { useEffect, useState } from "react";
import { Navigate, useParams, useSearchParams } from "react-router-dom";

import { NOTE_PREFIXES, useActivities, useAgentTasks } from "../../api/projectData";
import { WIP_NOTE } from "../../api/wip";
import { WipEditor } from "../data/DataTab";
import { TodayPanel } from "../data/TodayPanel";
import { Activities, AgentTasks } from "../data/TypedNotes";
import { noteZone } from "../project/redirects";

/** The zone «Lavoro» of a project, where it opens: «📌 Oggi» on top, then the
 * activities (an agent task opens inside the activity it is born from), every
 * agent task («Tutti i task»: also those without an activity) and the WIP note.
 * ``?note=`` says what is open, and so which view: an activity, an agent task
 * (inside its activity when it has one, unless «Tutti i task» is the chosen view)
 * or the WIP note. */

type View = "activities" | "tasks" | "wip";

export function WorkZone() {
  const { project = "" } = useParams();
  const [search, setSearch] = useSearchParams();
  const activities = useActivities(project);
  const tasks = useAgentTasks(project);
  const [chosen, setChosen] = useState<View | null>(null);
  const note = search.get("note");
  const isActivity = !!note?.startsWith(NOTE_PREFIXES.activity);
  const isTask = !!note?.startsWith(NOTE_PREFIXES.agent_task);
  useEffect(() => { if (isActivity || note === WIP_NOTE) setChosen(null); }, [note, isActivity]); // a link elsewhere ends the chosen view

  if (note && noteZone(note) === "project") { // a note or a reference (e.g. «Apri» on a linked one): it lives in «Progetto»
    return <Navigate to={`/projects/${encodeURIComponent(project)}/project?note=${encodeURIComponent(note)}`} replace />;
  }
  if (isTask && chosen !== "tasks" && activities.isPending) return <Loader size="sm" />; // which activity is it born from?
  const hasParent = isTask && !!activities.data?.some((activity) => activity.agent_tasks.includes(note!));
  const view: View = isActivity ? "activities" : note === WIP_NOTE ? "wip"
    : isTask ? (chosen === "tasks" || !hasParent ? "tasks" : "activities") : chosen ?? "activities";
  const change = (value: string | null) => {
    if (!value) return;
    setChosen(value as View);
    setSearch(value === "wip" ? { note: WIP_NOTE } : {}, { replace: true });
  };
  return (
    <>
      <TodayPanel project={project} />
      <Tabs value={view} onChange={change} keepMounted={false}>
        <Tabs.List mb="md">
          <Tabs.Tab value="activities">📋 Attività</Tabs.Tab>
          <Tabs.Tab value="tasks">🤖 Tutti i task{tasks.data ? ` (${tasks.data.length})` : ""}</Tabs.Tab>
          <Tabs.Tab value="wip">📥 WIP</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="activities"><Activities project={project} /></Tabs.Panel>
        <Tabs.Panel value="tasks"><AgentTasks project={project} /></Tabs.Panel>
        <Tabs.Panel value="wip"><WipEditor project={project} /></Tabs.Panel>
      </Tabs>
    </>
  );
}
