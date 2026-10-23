"""Graph rules of an automation (domain/pipeline/graph.py): pure, no store."""
import pytest

from core.error import ValidationError
from domain.pipeline.graph import (
    ancestors, join_outputs, linear_edges, passing_targets, topological_order, validate_graph,
)
from models.domain.pipeline import INPUT_NODE, EdgeConditionKind, PipelineEdge, PipelineStep, StepAgent, StepKind


def _step(name, template="{input}"):
    return PipelineStep(name=name, kind=StepKind.AGENT, input_template=template,
                        agent=StepAgent(system_prompt="x", model="openai/gpt-4o"))


def _edge(source, target, condition=EdgeConditionKind.ALWAYS, value=""):
    return PipelineEdge(source=source, target=target, condition=condition, value=value)


# input ─► Check ─(contains OK)─► Pull ─┐
#                 └(otherwise)─► Avvisa ├─► Fine
# input ─► Jira ────────────────────────┘
DIAMOND = [_step("Check"), _step("Jira"), _step("Pull"), _step("Avvisa"), _step("Fine")]
DIAMOND_EDGES = [
    _edge(INPUT_NODE, "Check"), _edge(INPUT_NODE, "Jira"),
    _edge("Check", "Pull", EdgeConditionKind.CONTAINS, "OK"), _edge("Check", "Avvisa", EdgeConditionKind.OTHERWISE),
    _edge("Pull", "Fine"), _edge("Avvisa", "Fine"), _edge("Jira", "Fine"),
]


def test_a_branching_graph_is_valid():
    validate_graph(DIAMOND, DIAMOND_EDGES)


def test_linear_edges_chain_the_steps_in_order():
    edges = linear_edges([_step("A"), _step("B")])

    assert [(e.source, e.target, e.condition) for e in edges] == [
        (INPUT_NODE, "A", EdgeConditionKind.ALWAYS), ("A", "B", EdgeConditionKind.ALWAYS),
    ]
    validate_graph([_step("A"), _step("B")], edges)


def test_topological_order_respects_edges_and_step_order_for_ties():
    assert topological_order(DIAMOND, DIAMOND_EDGES) == ["Check", "Jira", "Pull", "Avvisa", "Fine"]


def test_ancestors():
    assert ancestors("Fine", DIAMOND_EDGES) == {"Check", "Jira", "Pull", "Avvisa"}
    assert ancestors("Check", DIAMOND_EDGES) == set()


@pytest.mark.parametrize("steps, edges, message", [
    ([_step("A"), _step("a")], [_edge(INPUT_NODE, "A"), _edge(INPUT_NODE, "a")], "nomi devono essere unici"),
    ([_step("Input")], [_edge(INPUT_NODE, "Input")], "riservato"),
    ([_step("A")], [_edge(INPUT_NODE, "A"), _edge("A", "B")], "B non esiste"),
    ([_step("A")], [_edge(INPUT_NODE, "A"), _edge("A", INPUT_NODE)], "niente può entrare in input"),
    ([_step("A")], [_edge(INPUT_NODE, "A"), _edge("A", "A")], "se stesso"),
    ([_step("A")], [_edge(INPUT_NODE, "A"), _edge(INPUT_NODE, "A")], "c'è già"),
    ([_step("A"), _step("B")], [_edge(INPUT_NODE, "A")], "B non ha collegamenti in ingresso"),
    ([_step("A"), _step("B"), _step("C")],
     [_edge(INPUT_NODE, "A"), _edge("B", "C"), _edge("C", "B")], "ciclo"),
    ([_step("A"), _step("B")], [_edge(INPUT_NODE, "A"), _edge("A", "B", EdgeConditionKind.CONTAINS)], "vuole un testo"),
    ([_step("A"), _step("B")], [_edge(INPUT_NODE, "A"), _edge("A", "B", EdgeConditionKind.MATCHES, "(")], "regex non valida"),
    ([_step("A"), _step("B")], [_edge(INPUT_NODE, "A"), _edge("A", "B", EdgeConditionKind.OTHERWISE)], "accanto a collegamenti"),
    ([_step("A"), _step("B"), _step("C"), _step("D")],
     [_edge(INPUT_NODE, "A"), _edge("A", "B", EdgeConditionKind.CONTAINS, "x"),
      _edge("A", "C", EdgeConditionKind.OTHERWISE), _edge("A", "D", EdgeConditionKind.OTHERWISE)], "più collegamenti «altrimenti»"),
    ([_step("A"), _step("B", template="{nodo:C}"), _step("C")],
     [_edge(INPUT_NODE, "A"), _edge("A", "B"), _edge("A", "C")], "C non è uno step che lo precede"),
])
def test_invalid_graphs(steps, edges, message):
    with pytest.raises(ValidationError, match=message):
        validate_graph(steps, edges)


def test_node_placeholder_of_an_ancestor_is_fine():
    validate_graph([_step("A"), _step("B", template="{nodo:A} e {input}")], [_edge(INPUT_NODE, "A"), _edge("A", "B")])


# ----------------------------------------------------------- conditions

def test_passing_targets_text_conditions_and_otherwise():
    edges = [
        _edge("A", "Ok", EdgeConditionKind.CONTAINS, "ok"),
        _edge("A", "NoErr", EdgeConditionKind.NOT_CONTAINS, "errore"),
        _edge("A", "Num", EdgeConditionKind.MATCHES, r"RESEVO-\d+"),
        _edge("A", "Else", EdgeConditionKind.OTHERWISE),
        _edge("A", "Sempre"),
        _edge("B", "Altro"),
    ]

    assert passing_targets("A", "Tutto OK su resevo-12", edges) == ["Sempre", "Ok", "NoErr", "Num"]
    assert passing_targets("A", "c'è un errore", edges) == ["Sempre", "Else"]


def test_join_outputs():
    assert join_outputs([("Jira", "j")]) == "j"
    assert join_outputs([("Jira", "j"), ("Git", "g")]) == "## Jira\nj\n\n## Git\ng"
