import { describe, expect, it } from "vitest";

import type { Pipeline, Step } from "../../api/automation";
import { INPUT_NODE, addStep, connect, edgeId, edgeLabel, fromPipeline, removeEdge, removeStep, toRequest, updateEdge, updateStep } from "./graphDraft";

const step = (name: string, x = 0, y = 0): Step => ({
  name, kind: "function", input_template: "{input}", agent: null, agent_config_name: null,
  function_name: "git_status", params: {}, position_x: x, position_y: y,
});

const pipeline = (steps: Step[], edges: Pipeline["edges"]): Pipeline => ({
  id: 1, project_name: "acme", name: "P", description: "", active: true, steps, edges,
});

const uids = (draft: ReturnType<typeof fromPipeline>) =>
  Object.fromEntries(draft.order.map((uid) => [draft.steps[uid].name, uid]));

describe("graphDraft", () => {
  it("reads a saved automation with its conditions and positions", () => {
    const draft = fromPipeline(pipeline([step("Check", 10, 20), step("Pull", 300)], [
      { source: "input", target: "Check", condition: "always", value: "" },
      { source: "Check", target: "Pull", condition: "contains", value: "OK" },
    ]));

    const uid = uids(draft);
    expect(draft.edges.map((e) => [e.source, e.target, e.condition])).toEqual([
      [INPUT_NODE, uid.Check, "always"], [uid.Check, uid.Pull, "contains"],
    ]);
    expect([draft.steps[uid.Check].position_x, draft.steps[uid.Check].position_y]).toEqual([10, 20]);
    expect(edgeLabel(draft.edges[1])).toBe("contiene «OK»");
  });

  it("lays out in a row the steps never placed", () => {
    const draft = fromPipeline(pipeline([step("A"), step("B")], []));

    expect(draft.order.map((uid) => draft.steps[uid].position_x)).toEqual([240, 480]);
  });

  it("adds steps with a free name, right of the others", () => {
    const [draft, uid] = addStep(fromPipeline(pipeline([step("Step 2", 500)], [])), "agent", "openai/gpt-4o");

    expect(draft.steps[uid]).toMatchObject({ name: "Step 3", position_x: 740, kind: "agent" });
    expect(draft.steps[uid].agent?.model).toBe("openai/gpt-4o");
  });

  it("connects only valid, new edges", () => {
    let [draft, a] = addStep(fromPipeline(undefined), "function");
    let b: string;
    [draft, b] = addStep(draft, "function");
    draft = connect(draft, INPUT_NODE, a);
    draft = connect(draft, a, b);

    for (const [source, target] of [[a, b], [b, b], [b, INPUT_NODE], [a, "ghost"]]) {
      expect(connect(draft, source, target)).toBe(draft); // unchanged
    }
    expect(draft.edges.map(edgeId)).toEqual([`${INPUT_NODE}->${a}`, `${a}->${b}`]);
  });

  it("sends steps and edges by name, dropping values of non-text conditions", () => {
    const saved = fromPipeline(pipeline([step("A"), step("B")], [
      { source: "input", target: "A", condition: "always", value: "" },
      { source: "A", target: "B", condition: "always", value: "" },
    ]));
    const uid = uids(saved);
    let draft = updateStep(saved, uid.A, { name: " Analizza " }); // a rename keeps the edges
    draft = updateEdge(draft, `${uid.A}->${uid.B}`, { condition: "otherwise", value: "resto" });

    const { steps, edges } = toRequest(draft);

    expect(steps.map((s) => s.name)).toEqual(["Analizza", "B"]);
    expect(edges).toEqual([
      { source: "input", target: "Analizza", condition: "always", value: "" },
      { source: "Analizza", target: "B", condition: "otherwise", value: "" },
    ]);
  });

  it("removes a step with its edges, and single edges", () => {
    const saved = fromPipeline(pipeline([step("A"), step("B")], [
      { source: "input", target: "A", condition: "always", value: "" },
      { source: "A", target: "B", condition: "always", value: "" },
    ]));
    const uid = uids(saved);

    expect(removeStep(saved, uid.B).edges.map(edgeId)).toEqual([`${INPUT_NODE}->${uid.A}`]);
    expect(removeEdge(saved, `${INPUT_NODE}->${uid.A}`).edges.map(edgeId)).toEqual([`${uid.A}->${uid.B}`]);
  });
});
