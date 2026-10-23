"""The graph draft of the automation editor (ui/views/graph_draft.py): from a
saved automation, canvas changes absorbed, back to the API body. No Streamlit."""
from datetime import datetime, timezone

from api_client.models import Edge, Pipeline, Step, StepAgent
from views.graph_draft import INPUT_NODE, GraphDraft


def _step(name, x=0.0, y=0.0, kind="agent"):
    agent = StepAgent(system_prompt="Fai.", model="openai/gpt-4o") if kind == "agent" else None
    return Step(name=name, kind=kind, input_template="{input}", agent=agent, position_x=x, position_y=y)


def _pipeline(steps, edges):
    return Pipeline(id=1, project_name="acme", name="P", description="", active=True, steps=steps, edges=edges)


def _uids(draft):
    return {step.name: uid for uid, step in draft.nodes.items()}


def test_from_pipeline_keeps_edges_conditions_and_positions():
    pipeline = _pipeline([_step("Check", 10, 20), _step("Pull", 300, 0)], [
        Edge(source="input", target="Check"), Edge(source="Check", target="Pull", condition="contains", value="OK"),
    ])

    draft = GraphDraft.from_pipeline(pipeline)

    uid = _uids(draft)
    assert [(e.source, e.target, e.condition, e.value) for e in draft.edges] == [
        (INPUT_NODE, uid["Check"], "always", ""), (uid["Check"], uid["Pull"], "contains", "OK"),
    ]
    assert (draft.nodes[uid["Check"]].position_x, draft.nodes[uid["Check"]].position_y) == (10, 20)
    assert draft.edges[1].label == "contiene «OK»" and draft.edges[0].label == ""


def test_steps_never_placed_are_laid_out_in_a_row():
    draft = GraphDraft.from_pipeline(_pipeline([_step("A"), _step("B")], []))

    assert [step.position_x for step in draft.nodes.values()] == [240, 480]


def test_add_node_gets_a_free_name_and_goes_right():
    draft = GraphDraft.from_pipeline(_pipeline([_step("Step 2", 500)], []))

    uid = draft.add_node("function")

    assert draft.nodes[uid].name == "Step 3" and draft.nodes[uid].position_x == 740
    assert draft.nodes[uid].agent is None and draft.add_node("agent", "openai/gpt-4o") in draft.nodes


def test_absorb_moves_and_adds_edges_but_never_removes_anything():
    draft = GraphDraft()
    a, b, c = draft.add_node("agent"), draft.add_node("agent"), draft.add_node("agent")
    draft.absorb({}, [(INPUT_NODE, a), (a, b), (b, c)])
    draft.edge(f"{a}->{b}").condition, draft.edge(f"{a}->{b}").value = "contains", "OK"

    changed = draft.absorb(
        {INPUT_NODE: (-50, 5), a: (100, 7)},  # a partial echo: c and (b, c) missing, kept anyway
        [(INPUT_NODE, a), (a, b), (b, b), (b, INPUT_NODE), (a, b), (a, "ghost"), (INPUT_NODE, c)],
    )

    assert changed and c in draft.nodes
    assert draft.input_position == (-50, 5) and draft.nodes[a].position_x == 100
    assert [(e.source, e.target, e.condition) for e in draft.edges] == [
        (INPUT_NODE, a, "always"), (a, b, "contains"), (b, c, "always"), (INPUT_NODE, c, "always"),
    ]
    assert not draft.absorb({a: (1, 1)}, [])  # only a move, even with no edges reported


def test_to_request_uses_names_and_drops_values_of_non_text_conditions():
    draft = GraphDraft()
    a, b = draft.add_node("agent"), draft.add_node("agent")
    draft.nodes[a].name = " Check "
    draft.absorb({}, [(INPUT_NODE, a), (a, b)])
    draft.edges[1].condition, draft.edges[1].value = "otherwise", "resto"

    steps, edges = draft.to_request()

    assert [s.name for s in steps] == ["Check", "Step 2"]
    assert [(e.source, e.target, e.condition, e.value) for e in edges] == [
        ("input", "Check", "always", ""), ("Check", "Step 2", "otherwise", ""),
    ]


def test_renaming_a_step_keeps_its_edges():
    draft = GraphDraft.from_pipeline(_pipeline([_step("A"), _step("B")], [
        Edge(source="input", target="A"), Edge(source="A", target="B"),
    ]))
    draft.nodes[_uids(draft)["A"]].name = "Analizza"

    _, edges = draft.to_request()

    assert [(e.source, e.target) for e in edges] == [("input", "Analizza"), ("Analizza", "B")]


def test_remove_node_and_edge():
    draft = GraphDraft()
    a, b = draft.add_node("agent"), draft.add_node("agent")
    draft.absorb({}, [(INPUT_NODE, a), (a, b)])

    draft.remove_edge(f"{INPUT_NODE}->{a}")
    draft.remove_node(b)

    assert list(draft.nodes) == [a] and draft.edges == []
