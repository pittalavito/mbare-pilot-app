"""The graph of an automation: its steps are the nodes, the edges say which
output feeds which step and on which condition. Pure functions, no I/O.

Rules (``validate_graph``): step names unique and not ``input`` (the node of
the run input, where every graph starts); edges between existing nodes, never
into ``input``, no duplicates nor self-loops; no cycles; every step reachable
from ``input``; conditions with their value, valid regexes, at most one
``otherwise`` per node and only next to text conditions."""
import re
from collections import deque

from core.error import ValidationError
from models.domain.pipeline import INPUT_NODE, NODE_PLACEHOLDER, EdgeConditionKind, PipelineEdge, PipelineStep

_TEXT_CONDITIONS = {EdgeConditionKind.CONTAINS, EdgeConditionKind.NOT_CONTAINS, EdgeConditionKind.MATCHES}


def passing_targets(source: str, output: str, edges: list[PipelineEdge]) -> list[str]:
    """The targets of ``source`` whose edge lets ``output`` through: text
    conditions are case-insensitive (``matches`` is a regex), ``otherwise``
    passes when none of the text conditions of ``source`` passed."""
    outgoing = [edge for edge in edges if edge.source == source]
    passed = [edge for edge in outgoing if edge.condition in _TEXT_CONDITIONS and _holds(edge, output)]
    targets = [edge.target for edge in outgoing if edge.condition is EdgeConditionKind.ALWAYS] + [edge.target for edge in passed]
    if not passed:
        targets += [edge.target for edge in outgoing if edge.condition is EdgeConditionKind.OTHERWISE]
    return targets


def join_outputs(outputs: list[tuple[str, str]]) -> str:
    """One ``(node, output)``: the output itself. More: each under ``## node``."""
    if len(outputs) == 1:
        return outputs[0][1]
    return "\n\n".join(f"## {name}\n{output}" for name, output in outputs)


def _holds(edge: PipelineEdge, output: str) -> bool:
    if edge.condition is EdgeConditionKind.CONTAINS:
        return edge.value.lower() in output.lower()
    if edge.condition is EdgeConditionKind.NOT_CONTAINS:
        return edge.value.lower() not in output.lower()
    return re.search(edge.value, output, re.IGNORECASE) is not None


def linear_edges(steps: list[PipelineStep]) -> list[PipelineEdge]:
    """The chain ``input → first step → … → last step``: the graph of an
    automation saved without edges."""
    names = [INPUT_NODE, *(step.name for step in steps)]
    return [PipelineEdge(source=source, target=target) for source, target in zip(names, names[1:])]


def validate_graph(steps: list[PipelineStep], edges: list[PipelineEdge]) -> None:
    """ValidationError naming the first problem found."""
    names = _check_names(steps)
    _check_edges(names, edges)
    order = topological_order(steps, edges)  # raises on cycles
    reachable = _reachable(edges)
    for step in steps:
        if not any(edge.target == step.name for edge in edges):
            raise ValidationError(f"Lo step {step.name} non ha collegamenti in ingresso: collegalo a input o a un altro step.")
        if step.name not in reachable:
            raise ValidationError(f"Lo step {step.name} non è raggiungibile da input.")
    _check_placeholders(steps, edges, order)


def topological_order(steps: list[PipelineStep], edges: list[PipelineEdge]) -> list[str]:
    """Step names in an order where every step comes after the ones feeding
    it; ties follow the steps' order. ValidationError when there is a cycle."""
    position = {step.name: index for index, step in enumerate(steps)}
    incoming = {name: 0 for name in position}
    for edge in edges:
        if edge.target in incoming and edge.source != INPUT_NODE:
            incoming[edge.target] += 1
    ready = sorted((name for name, count in incoming.items() if count == 0), key=position.get)
    order: list[str] = []
    while ready:
        name = ready.pop(0)
        order.append(name)
        for edge in edges:
            if edge.source == name and edge.target in incoming:
                incoming[edge.target] -= 1
                if incoming[edge.target] == 0:
                    ready.append(edge.target)
                    ready.sort(key=position.get)
    if len(order) != len(position):
        stuck = ", ".join(name for name in position if name not in order)
        raise ValidationError(f"Il grafo ha un ciclo: {stuck} non possono partire mai.")
    return order


def ancestors(name: str, edges: list[PipelineEdge]) -> set[str]:
    """The steps whose output can reach ``name`` (``input`` excluded)."""
    found: set[str] = set()
    queue = deque([name])
    while queue:
        current = queue.popleft()
        for edge in edges:
            if edge.target == current and edge.source != INPUT_NODE and edge.source not in found:
                found.add(edge.source)
                queue.append(edge.source)
    return found


# ------------------------------------------------------------------ checks

def _check_names(steps: list[PipelineStep]) -> set[str]:
    seen: dict[str, str] = {}
    for step in steps:
        key = step.name.lower()
        if key == INPUT_NODE:
            raise ValidationError(f"«{step.name}» è riservato al nodo dell'input: scegli un altro nome per lo step.")
        if key in seen:
            raise ValidationError(f"Due step si chiamano {step.name}: i nomi devono essere unici.")
        seen[key] = step.name
    return {step.name for step in steps}


def _check_edges(names: set[str], edges: list[PipelineEdge]) -> None:
    pairs: set[tuple[str, str]] = set()
    for edge in edges:
        label = f"Collegamento {edge.source} → {edge.target}"
        if edge.source != INPUT_NODE and edge.source not in names:
            raise ValidationError(f"{label}: lo step {edge.source} non esiste.")
        if edge.target == INPUT_NODE:
            raise ValidationError(f"{label}: niente può entrare in input.")
        if edge.target not in names:
            raise ValidationError(f"{label}: lo step {edge.target} non esiste.")
        if edge.source == edge.target:
            raise ValidationError(f"{label}: uno step non può collegarsi a se stesso.")
        if (edge.source, edge.target) in pairs:
            raise ValidationError(f"{label}: c'è già.")
        pairs.add((edge.source, edge.target))
        if edge.condition in _TEXT_CONDITIONS and not edge.value:
            raise ValidationError(f"{label}: la condizione «{edge.condition.value}» vuole un testo.")
        if edge.condition is EdgeConditionKind.MATCHES:
            try:
                re.compile(edge.value)
            except re.error as exc:
                raise ValidationError(f"{label}: regex non valida ({exc}).") from exc
    for source in {edge.source for edge in edges}:
        outgoing = [edge for edge in edges if edge.source == source]
        otherwise = [edge for edge in outgoing if edge.condition is EdgeConditionKind.OTHERWISE]
        if len(otherwise) > 1:
            raise ValidationError(f"Da {source} escono più collegamenti «altrimenti»: ne basta uno.")
        if otherwise and not any(edge.condition in _TEXT_CONDITIONS for edge in outgoing):
            raise ValidationError(f"Da {source}: «altrimenti» serve solo accanto a collegamenti con una condizione sul testo.")


def _reachable(edges: list[PipelineEdge]) -> set[str]:
    found: set[str] = set()
    queue = deque([INPUT_NODE])
    while queue:
        current = queue.popleft()
        for edge in edges:
            if edge.source == current and edge.target not in found:
                found.add(edge.target)
                queue.append(edge.target)
    return found


def _check_placeholders(steps: list[PipelineStep], edges: list[PipelineEdge], order: list[str]) -> None:
    """``{nodo:Nome}`` only for a step that comes before, on a path into this one."""
    for step in steps:
        for referenced in NODE_PLACEHOLDER.findall(step.input_template):
            if referenced not in ancestors(step.name, edges):
                raise ValidationError(
                    f"Lo step {step.name} usa {{nodo:{referenced}}}, ma {referenced} non è uno step che lo precede."
                )
