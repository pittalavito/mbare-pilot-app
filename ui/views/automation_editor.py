"""Graph editor of an automation, shown in place of the Automation tab while
editing: a canvas (streamlit-flow) where steps are added, dragged and joined
by dragging from a node's right handle to another node's left handle, and a
panel under it to configure the selected step or edge (its condition).

The ``GraphDraft`` in session state is the source of truth: the canvas is
rebuilt from it whenever something changes here (a new node, a rename, a
condition), and what the user does on the canvas (moves, new edges) is absorbed back
into it. Steps and edges are removed only from the panel: right after a redraw
the canvas may echo a partial state, which must never delete anything."""
import streamlit as st
from streamlit_flow import streamlit_flow
from streamlit_flow.elements import StreamlitFlowEdge, StreamlitFlowNode
from streamlit_flow.state import StreamlitFlowState

from api_client.client import ApiError
from api_client.models import Function, Pipeline, StepAgent
from views.graph_draft import CONDITION_LABELS, INPUT_NODE, KIND_LABELS, TEXT_CONDITIONS, GraphDraft
from views.model_picker import model_select
from views.services import api

_CANVAS_HEIGHT = 480
_EDGE_ARROW = {"type": "arrowclosed", "width": 18, "height": 18}
_MAX_REDRAWS = 3


# ------------------------------------------------------------- entry points

def editing(project_name: str) -> int | str | None:
    """The automation being edited in the project (its id, or ``"new"``), None when not editing."""
    return st.session_state.get(_editing_key(project_name))


def open_editor(project_name: str, pipeline: Pipeline | None) -> None:
    base = _base(project_name, pipeline.id if pipeline else "new")
    for state_key in [k for k in st.session_state if str(k).startswith(f"{base}_")]:
        del st.session_state[state_key]
    st.session_state[f"{base}_draft"] = GraphDraft.from_pipeline(pipeline)
    st.session_state[_editing_key(project_name)] = pipeline.id if pipeline else "new"
    st.rerun()


def automation_editor(project_name: str, pipeline: Pipeline | None) -> None:
    base = _base(project_name, pipeline.id if pipeline else "new")
    draft: GraphDraft = st.session_state[f"{base}_draft"]

    col_title, col_back = st.columns([5, 1], vertical_alignment="bottom")
    col_title.subheader(f"✏️ {pipeline.name}" if pipeline else "➕ Nuova automation")
    col_back.button("← Annulla", width="stretch", key=f"{base}_cancel", on_click=_close, args=(project_name,))
    col_name, col_active = st.columns([4, 1], vertical_alignment="bottom")
    col_name.text_input("Nome", value=pipeline.name if pipeline else "", key=f"{base}_name")
    col_active.toggle("Attiva", value=pipeline.active if pipeline else True, key=f"{base}_active")
    st.text_input("Descrizione", value=pipeline.description if pipeline else "", key=f"{base}_description",
                  help="La legge anche il chatbot per scegliere quale automation lanciare.")

    _toolbar(base, draft)
    selected = _canvas(base, draft)  # full width: the graph needs the room
    _panel(base, project_name, draft, selected)

    st.divider()
    if error := st.session_state.pop(f"{base}_error", None):
        st.error(error)
    col_save, col_delete, _ = st.columns([1, 1, 3], vertical_alignment="bottom")
    col_save.button("💾 Salva", type="primary", width="stretch", key=f"{base}_save",
                    on_click=_save, args=(base, project_name, pipeline, draft))
    if pipeline is not None:
        with col_delete.popover("Elimina automation", width="stretch"):
            st.write(f"Eliminare **{pipeline.name}** e il suo storico? Le run degli agenti restano.")
            st.button("Sì, elimina", type="primary", key=f"{base}_delete", on_click=_delete, args=(project_name, pipeline))


# ------------------------------------------------------------------ toolbar

def _toolbar(base: str, draft: GraphDraft) -> None:
    st.caption("Aggiungi gli step, collegali trascinando dal pallino destro di un nodo al pallino sinistro di un altro, "
               "clicca un nodo o un collegamento per configurarlo o eliminarlo (🗑). `input` è l'input dell'esecuzione.")
    columns = st.columns(len(KIND_LABELS) + 1)
    for column, (kind, label) in zip(columns, KIND_LABELS.items()):
        column.button(f"➕ {label}", width="stretch", key=f"{base}_add_{kind}", on_click=_add_node, args=(base, draft, kind))


# Buttons that change the graph act in callbacks: a click read as the return
# value of st.button can be lost when the canvas sends its state at the same
# time (it does right after it is drawn); callbacks always run.

def _add_node(base: str, draft: GraphDraft, kind: str) -> None:
    default_model = next(iter(api().agents.model_choices().usable), None)
    st.session_state[f"{base}_select"] = draft.add_node(kind, default_model)


def _remove_node(draft: GraphDraft, uid: str) -> None:
    draft.remove_node(uid)


def _remove_edge(draft: GraphDraft, edge_id: str) -> None:
    draft.remove_edge(edge_id)


# ------------------------------------------------------------------- canvas

def _canvas(base: str, draft: GraphDraft) -> str | None:
    """Draw the graph; absorb what the user did. Returns the selected node or edge id."""
    signature = _signature(draft)
    forced = st.session_state.pop(f"{base}_select", None)
    if st.session_state.get(f"{base}_signature") != signature or forced:
        # Redrawn after a change made here: keep what was selected (e.g. the edge whose condition changed).
        keep = forced if forced is not None else st.session_state.get(f"{base}_selected")
        st.session_state[f"{base}_flow"] = _flow_state(draft, keep)
        st.session_state[f"{base}_signature"] = signature
        forced = keep
    passed = st.session_state[f"{base}_flow"]
    state = streamlit_flow(
        f"{base}_canvas", passed, height=_CANVAS_HEIGHT, fit_view=True,
        allow_new_edges=True, get_node_on_click=True, get_edge_on_click=True, hide_watermark=True,
    )
    if state.timestamp < passed.timestamp:
        # Streamlit hands back the canvas' last value even after the graph was
        # changed here: older than what was just drawn, so not the user's doing.
        selected = forced or passed.selected_id
    else:
        st.session_state[f"{base}_flow"] = state
        changed = draft.absorb(
            {node.id: (node.position["x"], node.position["y"]) for node in state.nodes},
            [(edge.source, edge.target) for edge in state.edges],
        )
        if changed:  # redraw from the draft: drawn edges get their ids and labels
            st.session_state[f"{base}_select"] = state.selected_id or ""
            st.rerun()
        if _canvas_lags(draft, state):
            # streamlit-flow re-runs its layout on the nodes it had before an
            # update and sends that back: the canvas lost part of the draft.
            # Redraw it (a few times at most, never in a loop).
            retries = st.session_state.get(f"{base}_retries", 0)
            if retries < _MAX_REDRAWS:
                st.session_state[f"{base}_retries"] = retries + 1
                st.session_state[f"{base}_signature"] = None
                st.rerun()
        else:
            st.session_state[f"{base}_retries"] = 0
        # After a redraw the canvas echoes its state without a selection: the
        # selection stays until the user picks something else.
        selected = state.selected_id or st.session_state.get(f"{base}_selected")
    st.session_state[f"{base}_selected"] = selected
    return selected


def _canvas_lags(draft: GraphDraft, state: StreamlitFlowState) -> bool:
    """The canvas is missing steps or edges of the draft."""
    nodes = {node.id for node in state.nodes}
    edges = {(edge.source, edge.target) for edge in state.edges}
    return (not set(draft.nodes) <= nodes) or any((e.source, e.target) not in edges for e in draft.edges)


def _signature(draft: GraphDraft) -> tuple:
    """What the canvas shows besides positions: a change here redraws it."""
    return (
        tuple((uid, draft.node_label(uid)) for uid in draft.nodes),
        tuple((edge.id, edge.label) for edge in draft.edges),
    )


def _flow_state(draft: GraphDraft, selected: str | None) -> StreamlitFlowState:
    nodes = [StreamlitFlowNode(
        INPUT_NODE, draft.input_position, {"content": "📥 **input**"}, "input", "right",
        connectable=True, selectable=True, style={"background": "#e8f0fe", "color": "#1a1a1a"},
    )]
    for uid, step in draft.nodes.items():
        nodes.append(StreamlitFlowNode(
            uid, (step.position_x, step.position_y), {"content": draft.node_label(uid)}, "default", "right", "left",
            selected=uid == selected, connectable=True, selectable=True,
            style={"color": "#1a1a1a", "minWidth": "150px"},
        ))
    edges = [StreamlitFlowEdge(
        edge.id, edge.source, edge.target, label=edge.label, label_show_bg=True, marker_end=_EDGE_ARROW,
        focusable=True, selected=edge.id == selected,
        animated=edge.condition != "always",
    ) for edge in draft.edges]
    return StreamlitFlowState(nodes=nodes, edges=edges, selected_id=selected)


# -------------------------------------------------------------------- panel

def _panel(base: str, project_name: str, draft: GraphDraft, selected: str | None) -> None:
    if selected in draft.nodes:
        with st.container(border=True):
            _node_panel(base, project_name, draft, selected)
    elif selected and draft.edge(selected):
        with st.container(border=True):
            _edge_panel(base, draft, selected)
    else:
        st.info("Clicca uno step per configurarlo, o un collegamento per la sua condizione.")
        st.caption("Nel template dell'input: `{input}` = l'output che arriva (più ingressi: uniti per nome), "
                   "`{nodo:Nome}` = l'output di uno step precedente, `{pipeline_input}` = l'input dell'esecuzione.")


def _node_panel(base: str, project_name: str, draft: GraphDraft, uid: str) -> None:
    step = draft.nodes[uid]
    key = f"{base}_{uid}"
    col_title, col_remove = st.columns([4, 1], vertical_alignment="center")
    col_title.markdown(f"**Step** · {KIND_LABELS.get(step.kind, step.kind)}")
    col_remove.button("🗑", key=f"{key}_remove", help="Elimina lo step e i suoi collegamenti", width="stretch",
                      on_click=_remove_node, args=(draft, uid))
    step.name = st.text_input("Nome", value=step.name, key=f"{key}_name")
    kinds = list(KIND_LABELS)
    kind = st.selectbox("Tipo", kinds, index=kinds.index(step.kind), format_func=KIND_LABELS.get, key=f"{key}_kind")
    if kind != step.kind:
        step.kind = kind
        if kind == "agent" and step.agent is None:
            step.agent = StepAgent(system_prompt="", model=next(iter(api().agents.model_choices().usable), ""))
        st.rerun()
    step.input_template = st.text_area("Template dell'input", value=step.input_template, height=68, key=f"{key}_template")

    if step.kind == "agent":
        _agent_fields(key, step)
    elif step.kind == "agent_config":
        agents = {agent.name: agent for agent in api().agents.agents(project_name, include_global=True)}
        if not agents:
            st.info("Nessun agente nella Libreria o nel progetto.")
            return
        names = list(agents)
        index = names.index(step.agent_config_name) if step.agent_config_name in names else 0
        step.agent_config_name = st.selectbox(
            "Agente", names, index=index, key=f"{key}_agent",
            format_func=lambda name: f"{name} ({'progetto' if agents[name].project_name else 'globale'})",
        )
    else:
        functions = {spec.name: spec for spec in api().automation.functions()}
        names = list(functions)
        index = names.index(step.function_name) if step.function_name in names else 0
        function_name = st.selectbox("Funzione", names, index=index, key=f"{key}_function")
        if function_name != step.function_name:
            step.function_name, step.params = function_name, {}
        st.caption(functions[function_name].description)
        _params_fields(key, step, functions[function_name])


def _agent_fields(key: str, step) -> None:
    agent = step.agent
    agent.system_prompt = st.text_area("System prompt", value=agent.system_prompt, height=120, key=f"{key}_prompt",
                                       placeholder="Cosa fa questo step e come deve rispondere…")
    col_model, col_steps = st.columns([3, 1])
    agent.model = model_select(col_model, agent.model or None, key=f"{key}_model") or ""
    agent.max_steps = int(col_steps.number_input("Max steps", min_value=1, max_value=50, value=agent.max_steps,
                                                 key=f"{key}_max_steps"))
    tools = [tool.name for tool in api().agents.tools() if tool.available]
    agent.tool_names = st.multiselect("Tool", tools, default=[t for t in agent.tool_names if t in tools], key=f"{key}_tools")


def _params_fields(key: str, step, spec: Function) -> None:
    """One widget per parameter, by type (keys include the function name)."""
    for param in spec.params:
        value = step.params.get(param.name, param.default)
        label = param.name.replace("_", " ").capitalize()
        widget_key = f"{key}_param_{spec.name}_{param.name}"
        if param.type == "bool":
            step.params[param.name] = st.checkbox(label, value=bool(value), key=widget_key, help=param.description)
        elif param.type == "int":
            step.params[param.name] = int(st.number_input(label, value=int(value or 0), step=1, key=widget_key,
                                                          help=param.description))
        elif param.type == "float":
            step.params[param.name] = float(st.number_input(label, value=float(value or 0.0), step=0.1, key=widget_key,
                                                            help=param.description))
        else:
            step.params[param.name] = st.text_input(label, value="" if value is None else str(value), key=widget_key,
                                                    help=param.description)


def _edge_panel(base: str, draft: GraphDraft, edge_id: str) -> None:
    edge = draft.edge(edge_id)
    source = "input" if edge.source == INPUT_NODE else draft.nodes[edge.source].name
    key = f"{base}_{edge_id}"
    col_title, col_remove = st.columns([4, 1], vertical_alignment="center")
    col_title.markdown(f"**Collegamento** · {source} → {draft.nodes[edge.target].name}")
    col_remove.button("🗑", key=f"{key}_remove", help="Elimina il collegamento", width="stretch",
                      on_click=_remove_edge, args=(draft, edge_id))
    conditions = list(CONDITION_LABELS)
    edge.condition = st.selectbox("Quando passa l'output", conditions, index=conditions.index(edge.condition),
                                  format_func=CONDITION_LABELS.get, key=f"{key}_condition")
    if edge.condition in TEXT_CONDITIONS:
        placeholder = "es. RESEVO-\\d+" if edge.condition == "matches" else "es. OK"
        edge.value = st.text_input("Testo" if edge.condition != "matches" else "Regex", value=edge.value,
                                   placeholder=placeholder, key=f"{key}_value")
        st.caption("Maiuscole e minuscole indifferenti.")
    elif edge.condition == "otherwise":
        st.caption("Passa se nessun'altra condizione sul testo che esce dallo stesso step è vera.")


# --------------------------------------------------------------------- save

# Callbacks too (see _add_node): the canvas may rerun the script before the
# buttons are reached, which would lose a click read as a return value.

def _save(base: str, project_name: str, pipeline: Pipeline | None, draft: GraphDraft) -> None:
    name = st.session_state.get(f"{base}_name", "")
    description = st.session_state.get(f"{base}_description", "")
    active = st.session_state.get(f"{base}_active", True)
    steps, edges = draft.to_request()
    if steps and not edges:
        st.session_state[f"{base}_error"] = "Collega gli step: parti da `input` e trascina fino al primo step."
        return
    try:
        if pipeline is None:
            saved = api().automation.create_pipeline(project_name, name, description, active, steps, edges)
        else:
            saved = api().automation.update_pipeline(pipeline.id, name, description, active, steps, edges)
    except ApiError as exc:
        st.session_state[f"{base}_error"] = str(exc)
        return
    st.session_state[f"automation_{project_name}_select"] = saved.id
    _close(project_name)


def _delete(project_name: str, pipeline: Pipeline) -> None:
    api().automation.delete_pipeline(pipeline.id)
    _close(project_name)


def _close(project_name: str) -> None:
    """Leaves the editor (the script reruns right after the callback)."""
    st.session_state.pop(_editing_key(project_name), None)


def _editing_key(project_name: str) -> str:
    return f"automation_{project_name}_editing"


def _base(project_name: str, pipeline_id: int | str) -> str:
    return f"graph_{project_name}_{pipeline_id}"
