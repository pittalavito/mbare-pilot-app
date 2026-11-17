import { NOTE_PREFIXES } from "../../api/projectData";
import { WIP_NOTE } from "../../api/wip";

/** Where a note lives: activities, agent tasks and the WIP note in «Lavoro», the rest in «Progetto». */
export function noteZone(note: string | null): "work" | "project" {
  if (!note) return "work";
  return note === WIP_NOTE || note.startsWith(NOTE_PREFIXES.activity) || note.startsWith(NOTE_PREFIXES.agent_task) ? "work" : "project";
}
