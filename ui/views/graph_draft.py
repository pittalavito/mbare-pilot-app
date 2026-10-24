"""The automation being edited, as a graph draft: nodes (the steps, keyed by
a stable uid, so a rename keeps its edges) and edges between uids (``input``
is the run input). Pure Python, no Streamlit: the editor view draws it with
streamlit-flow and feeds back what the user did on the canvas.

Converts from a saved automation (``from_pipeline``) and to the API body
(``to_request``: steps and edges by step name)."""
import uuid
from dataclasses import dataclass, field

from api_client.models import Edge, Pipeline, Step, StepAgent

INPUT_NODE = "input"
KIND_LABELS = {"agent": "Agente proprio", "agent_config": "Agente della Libreria", "function": "Funzione (codice)"}
KIND_ICONS = {"agent": "🤖", "agent_config": "📚", "function": "⚙️"}
CONDITION_LABELS = {
    "always": "Sempre",
    "contains": "Se contiene",
    "not_contains": "Se non contiene",
    "matches": "Se corrisponde alla regex",
    "otherwise": "Altrimenti",
}
TEXT_CONDITIONS = ("contains", "not_contains", "matches")
_SPACING_X, _SPACING_Y = 240.0, 120.0


@dataclass
class DraftEdge:
    source: str
    """A node uid, or ``input``."""
    target: str
    condition: str = "always"
    value: str = ""

    @property
    def id(self) -> str:
        return f"{self.source}->{self.target}"

    @property
    def label(self) -> str:
        if self.condition == "always":
            return ""
        if self.condition == "otherwise":
            return "altrimenti"
        short = {"contains": "contiene", "not_contains": "non contiene", "matches": "regex"}[self.condition]
        return f"{short} «{self.value}»"


@dataclass
class GraphDraft:
    nodes: dict[str, Step] = field(default_factory=dict)
    """uid → step (name, kind, configuration, position)."""
    edges: list[DraftEdge] = field(default_factory=list)
    input_position: tuple[float, float] = (0.0, 0.0)
    """Where the ``input`` node is drawn (not saved: it is always there)."""

    # ------------------------------------------------------------ build
    @classmethod
    def from_pipeline(cls, pipeline: Pipeline | None) -> "GraphDraft":
        """The draft of a saved automation (None = an empty one). Nodes all at
        (0, 0), as saved before the graph editor existed, are laid out in a row;
        otherwise the graph is moved to start right of ``input``, keeping its shape."""
        draft = cls()
        if pipeline is None:
            return draft
        uid_by_name = {}
        for step in pipeline.steps:
            uid = _uid()
            draft.nodes[uid] = step.model_copy(deep=True)
            uid_by_name[step.name] = uid
        for edge in pipeline.edges:
            source = INPUT_NODE if edge.source == INPUT_NODE else uid_by_name.get(edge.source)
            target = uid_by_name.get(edge.target)
            if source and target:
                draft.edges.append(DraftEdge(source, target, edge.condition, edge.value))
        steps = list(draft.nodes.values())
        if steps and all(s.position_x == 0 and s.position_y == 0 for s in steps):
            for index, step in enumerate(steps, start=1):
                step.position_x, step.position_y = index * _SPACING_X, 0.0
        elif steps:  # moved as a whole to start right of input (where it is is not saved)
            dx = _SPACING_X - min(s.position_x for s in steps)
            dy = -min(s.position_y for s in steps)
            for step in steps:
                step.position_x, step.position_y = step.position_x + dx, step.position_y + dy
        first = [draft.nodes[e.target] for e in draft.edges if e.source == INPUT_NODE]
        draft.input_position = (0.0, sum(s.position_y for s in first) / len(first) if first else 0.0)
        return draft

    def add_node(self, kind: str, default_model: str | None = None) -> str:
        """A new step of ``kind`` with a free name, right of the others; its uid."""
        uid = _uid()
        number = len(self.nodes) + 1
        names = {step.name.lower() for step in self.nodes.values()}
        while f"step {number}" in names:
            number += 1
        right = max((step.position_x for step in self.nodes.values()), default=0.0)
        agent = StepAgent(system_prompt="", model=default_model or "") if kind == "agent" else None
        self.nodes[uid] = Step(
            name=f"Step {number}", kind=kind, input_template="{input}", agent=agent,
            position_x=right + _SPACING_X, position_y=_SPACING_Y * (len(self.nodes) % 2),
        )
        return uid

    def remove_node(self, uid: str) -> None:
        self.nodes.pop(uid, None)
        self.edges = [edge for edge in self.edges if uid not in (edge.source, edge.target)]

    def edge(self, edge_id: str) -> DraftEdge | None:
        return next((edge for edge in self.edges if edge.id == edge_id), None)

    def remove_edge(self, edge_id: str) -> None:
        self.edges = [edge for edge in self.edges if edge.id != edge_id]

    # ------------------------------------------------------- from the canvas
    def absorb(self, positions: dict[str, tuple[float, float]], edge_pairs: list[tuple[str, str]]) -> bool:
        """What the canvas reports: node positions and the edges drawn; new
        edges come in as ``always``. Nothing is ever removed from here (steps
        and edges go only with ``remove_node`` / ``remove_edge``, from the side
        panel): right after a redraw the canvas may echo a partial state, which
        must not lose anything. Edges into ``input``, a node into itself or to
        unknown nodes are ignored. True when edges were added."""
        for uid, (x, y) in positions.items():
            if uid == INPUT_NODE:
                self.input_position = (x, y)
            elif uid in self.nodes:
                self.nodes[uid].position_x, self.nodes[uid].position_y = x, y
        pairs = [(s, t) for s, t in edge_pairs if t != INPUT_NODE and s != t and t in self.nodes
                 and (s == INPUT_NODE or s in self.nodes)]
        known = {(edge.source, edge.target) for edge in self.edges}
        new = [DraftEdge(s, t) for s, t in dict.fromkeys(pairs) if (s, t) not in known]
        self.edges += new
        return bool(new)

    # ------------------------------------------------------------- labels
    def node_label(self, uid: str) -> str:
        step = self.nodes[uid]
        return f"{KIND_ICONS.get(step.kind, '')} **{step.name}**  \n{KIND_LABELS.get(step.kind, step.kind)}"

    # ------------------------------------------------------------- to API
    def to_request(self) -> tuple[list[Step], list[Edge]]:
        """Steps and edges by step name, as the API wants them."""
        names = {uid: step.name.strip() for uid, step in self.nodes.items()}
        steps = [step.model_copy(update={"name": names[uid]}) for uid, step in self.nodes.items()]
        edges = [
            Edge(source=INPUT_NODE if edge.source == INPUT_NODE else names[edge.source], target=names[edge.target],
                 condition=edge.condition, value=edge.value if edge.condition in TEXT_CONDITIONS else "")
            for edge in self.edges
        ]
        return steps, edges


def _uid() -> str:
    return "n" + uuid.uuid4().hex[:8]
