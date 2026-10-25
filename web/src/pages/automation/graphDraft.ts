import type { Edge, Pipeline, Step } from "../../api/automation";

/** The automation being edited, as a graph draft: steps keyed by a stable uid
 * (a rename keeps its edges) and edges between uids (``input`` is the run's
 * input). Pure functions returning new drafts: React state, no API. Converts
 * from a saved automation and to the API body (steps and edges by name). */

export const INPUT_NODE = "input";
export type Kind = "agent" | "agent_config" | "function";
export type Condition = "always" | "contains" | "not_contains" | "matches" | "otherwise";

export const KIND_LABELS: Record<Kind, string> = {
  agent: "Agente proprio",
  agent_config: "Agente della Libreria",
  function: "Funzione (codice)",
};
export const KIND_ICONS: Record<Kind, string> = { agent: "🤖", agent_config: "📚", function: "⚙️" };
export const CONDITION_LABELS: Record<Condition, string> = {
  always: "Sempre",
  contains: "Se contiene",
  not_contains: "Se non contiene",
  matches: "Se corrisponde alla regex",
  otherwise: "Altrimenti",
};
export const TEXT_CONDITIONS: Condition[] = ["contains", "not_contains", "matches"];

const SPACING_X = 240;
const SPACING_Y = 120;

export type DraftEdge = { source: string; target: string; condition: Condition; value: string };
export type Draft = {
  steps: Record<string, Step>;
  /** Uids in the order of the steps (it breaks ties in the execution order). */
  order: string[];
  edges: DraftEdge[];
};

export const edgeId = (edge: Pick<DraftEdge, "source" | "target">) => `${edge.source}->${edge.target}`;

export function edgeLabel(edge: DraftEdge): string {
  if (edge.condition === "always") return "";
  if (edge.condition === "otherwise") return "altrimenti";
  const short = { contains: "contiene", not_contains: "non contiene", matches: "regex" }[edge.condition];
  return `${short} «${edge.value}»`;
}

let counter = 0;
const newUid = () => `n${Date.now().toString(36)}${(counter++).toString(36)}`;

/** The draft of a saved automation (undefined = a new one). Steps all at
 * (0, 0), as saved before the graph editor existed, are laid out in a row. */
export function fromPipeline(pipeline: Pipeline | undefined): Draft {
  const draft: Draft = { steps: {}, order: [], edges: [] };
  if (!pipeline) return draft;
  const uidByName: Record<string, string> = {};
  for (const step of pipeline.steps) {
    const uid = newUid();
    draft.steps[uid] = structuredClone(step);
    draft.order.push(uid);
    uidByName[step.name] = uid;
  }
  for (const edge of pipeline.edges) {
    const source = edge.source === INPUT_NODE ? INPUT_NODE : uidByName[edge.source];
    const target = uidByName[edge.target];
    if (source && target) {
      draft.edges.push({ source, target, condition: (edge.condition ?? "always") as Condition, value: edge.value ?? "" });
    }
  }
  const steps = draft.order.map((uid) => draft.steps[uid]);
  if (steps.length && steps.every((step) => !step.position_x && !step.position_y)) {
    steps.forEach((step, index) => {
      step.position_x = (index + 1) * SPACING_X;
      step.position_y = 0;
    });
  }
  return draft;
}

/** A new step of ``kind`` with a free name, right of the others; the new draft and its uid. */
export function addStep(draft: Draft, kind: Kind, defaultModel = ""): [Draft, string] {
  const uid = newUid();
  const names = new Set(Object.values(draft.steps).map((step) => step.name.toLowerCase()));
  let number = draft.order.length + 1;
  while (names.has(`step ${number}`)) number += 1;
  const right = Math.max(0, ...Object.values(draft.steps).map((step) => step.position_x ?? 0));
  const step: Step = {
    name: `Step ${number}`,
    kind,
    input_template: "{input}",
    agent: kind === "agent" ? { system_prompt: "", prompt_version: 1, model: defaultModel, max_steps: 4, tool_names: [] } : null,
    agent_config_name: null,
    function_name: null,
    params: {},
    position_x: right + SPACING_X,
    position_y: SPACING_Y * (draft.order.length % 2),
  };
  return [{ ...draft, steps: { ...draft.steps, [uid]: step }, order: [...draft.order, uid] }, uid];
}

export function updateStep(draft: Draft, uid: string, patch: Partial<Step>): Draft {
  return { ...draft, steps: { ...draft.steps, [uid]: { ...draft.steps[uid], ...patch } } };
}

/** Change a step's kind: an own agent gets an empty agent to fill in. */
export function changeKind(draft: Draft, uid: string, kind: Kind, defaultModel = ""): Draft {
  const step = draft.steps[uid];
  const agent = kind === "agent" ? (step.agent ?? { system_prompt: "", prompt_version: 1, model: defaultModel, max_steps: 4, tool_names: [] }) : step.agent;
  return updateStep(draft, uid, { kind, agent });
}

export function removeStep(draft: Draft, uid: string): Draft {
  const { [uid]: _removed, ...steps } = draft.steps;
  return {
    steps,
    order: draft.order.filter((item) => item !== uid),
    edges: draft.edges.filter((edge) => edge.source !== uid && edge.target !== uid),
  };
}

/** A new edge, always passing; none into ``input``, into itself, to unknown nodes or twice. */
export function connect(draft: Draft, source: string, target: string): Draft {
  const known = (id: string) => id === INPUT_NODE || id in draft.steps;
  if (target === INPUT_NODE || source === target || !known(source) || !(target in draft.steps)) return draft;
  if (draft.edges.some((edge) => edge.source === source && edge.target === target)) return draft;
  return { ...draft, edges: [...draft.edges, { source, target, condition: "always", value: "" }] };
}

export function updateEdge(draft: Draft, id: string, patch: Partial<DraftEdge>): Draft {
  return { ...draft, edges: draft.edges.map((edge) => (edgeId(edge) === id ? { ...edge, ...patch } : edge)) };
}

export function removeEdge(draft: Draft, id: string): Draft {
  return { ...draft, edges: draft.edges.filter((edge) => edgeId(edge) !== id) };
}

export function moveStep(draft: Draft, uid: string, x: number, y: number): Draft {
  return updateStep(draft, uid, { position_x: x, position_y: y });
}

/** Steps and edges by step name, as the API wants them. */
export function toRequest(draft: Draft): { steps: Step[]; edges: Edge[] } {
  const names: Record<string, string> = {};
  for (const uid of draft.order) names[uid] = draft.steps[uid].name.trim();
  const steps = draft.order.map((uid) => ({ ...draft.steps[uid], name: names[uid] }));
  const edges = draft.edges.map((edge) => ({
    source: edge.source === INPUT_NODE ? INPUT_NODE : names[edge.source],
    target: names[edge.target],
    condition: edge.condition,
    value: TEXT_CONDITIONS.includes(edge.condition) ? edge.value : "",
  }));
  return { steps, edges };
}
