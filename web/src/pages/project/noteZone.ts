import { NOTE_PREFIXES } from "../../api/projectData";
import { WIP_NOTE } from "../../api/wip";

/** An archived activity's summary (plan 33): ``archivio-<attività>.md``, in «Lavoro» → «🗄 Archivio». */
export const ARCHIVE_PREFIX = "archivio-";

/** Where a note lives: activities, agent tasks, archived activities and the WIP note in «Lavoro», the rest in «Progetto». */
export function noteZone(note: string | null): "work" | "project" {
  if (!note) return "work";
  return note === WIP_NOTE || note.startsWith(NOTE_PREFIXES.activity) || note.startsWith(NOTE_PREFIXES.agent_task) || note.startsWith(ARCHIVE_PREFIX)
    ? "work" : "project";
}
