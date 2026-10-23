"""Automation tab of a project: its pipelines (created and edited here, with a
step editor), «Esegui» to queue a run for the worker, and the run history,
refreshed every few seconds while a run is queued or running."""
import uuid

import streamlit as st

from api_client.client import ApiError
from api_client.models import Function, Pipeline, PipelineRun, Step, StepAgent
from views.model_picker import model_select
from views.services import api

INPUT = "{input}"
PIPELINE_INPUT = "{pipeline_input}"
_KIND_LABELS = {
    "agent": "Agente proprio",
    "agent_config": "Agente della Libreria",
    "function": "Funzione (codice)",
}
_STATUS_ICONS = {"queued": "⏳", "running": "🔄", "done": "✅", "failed": "❌"}
_REFRESH_SECONDS = 2


def automation_section(project_name: str) -> None:
    key = f"automation_{project_name}"
    pipelines = api().automation.pipelines(project_name)
    if not pipelines:
        st.info("Nessuna automation: creane una con i suoi step (agenti che si passano il risultato).")
        if st.button("➕ Nuova automation", type="primary", key=f"{key}_first"):
            _open_editor(project_name, None)
        return

    by_id = {pipeline.id: pipeline for pipeline in pipelines}
    selected_key = f"{key}_pipeline"
    if f"{key}_select" in st.session_state:  # just created in the editor
        st.session_state[selected_key] = st.session_state.pop(f"{key}_select")
    if st.session_state.get(selected_key) not in by_id:
        st.session_state[selected_key] = pipelines[0].id

    col_pick, col_new, col_edit = st.columns([4, 1, 1], vertical_alignment="bottom")
    pipeline = by_id[col_pick.selectbox(
        "Automation", list(by_id), format_func=lambda pipeline_id: by_id[pipeline_id].name, key=selected_key,
    )]
    if col_new.button("➕ Nuova", width="stretch", key=f"{key}_new"):
        _open_editor(project_name, None)
    if col_edit.button("✏️ Modifica", width="stretch", key=f"{key}_edit"):
        _open_editor(project_name, pipeline)

    if pipeline.description:
        st.caption(pipeline.description)
    st.caption(" → ".join(f"**{position}.** {_step_label(step)}" for position, step in enumerate(pipeline.steps, start=1))
               or "Nessuno step: aggiungili con ✏️ Modifica.")
    if not pipeline.active:
        st.warning("Automation disattivata: riattivala da ✏️ Modifica per eseguirla.")

    _run_form(pipeline, key)
    _runs(pipeline)


# --------------------------------------------------------------------- runs

def _run_form(pipeline: Pipeline, key: str) -> None:
    with st.form(f"{key}_{pipeline.id}_run", clear_on_submit=True, border=True):
        pipeline_input = st.text_area(
            "Input", height=80, placeholder=f"Il testo che riceve il primo step come {INPUT} (anche vuoto).",
        )
        if st.form_submit_button("▶️ Esegui", type="primary", disabled=not pipeline.active or not pipeline.steps):
            try:
                api().automation.enqueue(pipeline.id, pipeline_input)
            except ApiError as exc:
                st.error(str(exc))
            else:
                st.toast("Esecuzione in coda: la esegue il worker.")
    if api().automation.waiting_too_long():
        st.warning("Ci sono esecuzioni in coda da più di 15 secondi: il worker è avviato? "
                   "Avvialo dalla barra laterale (Backend → Worker automation).")


def _runs(pipeline: Pipeline) -> None:
    """The history; refreshes itself while a run is queued or running."""
    runs = api().automation.runs(pipeline.id)
    in_progress = any(not run.finished for run in runs)
    st.fragment(_runs_view, run_every=_REFRESH_SECONDS if in_progress else None)(pipeline, in_progress)


def _runs_view(pipeline: Pipeline, was_in_progress: bool) -> None:
    runs = api().automation.runs(pipeline.id)
    if was_in_progress and all(run.finished for run in runs):
        st.rerun(scope="app")  # stop refreshing
    st.subheader("Esecuzioni")
    if not runs:
        st.caption("Nessuna esecuzione.")
    for run in runs:
        with st.expander(_run_title(pipeline.name, run), expanded=run is runs[0] and run.status != "done"):
            _run_detail(run)


def _run_detail(run: PipelineRun) -> None:
    """Input once, then each step; a step's input is shown only when its
    template changed it (otherwise it is the run input or the previous output,
    already on screen)."""
    st.markdown("**Input**")
    if run.input:
        st.text(run.input)
    else:
        st.caption("(vuoto)")
    if run.error and not any(step.error for step in run.steps):  # e.g. worker stopped, automation deleted
        st.error(run.error)

    previous = run.input
    for step in run.steps:
        with st.container(border=True):
            duration = f" · {_seconds(step.started_at, step.finished_at)}" if step.started_at and step.finished_at else ""
            st.markdown(f"{_STATUS_ICONS.get(step.status, '')} **{step.position + 1}. {step.name}**")
            st.caption(f"{_KIND_LABELS.get(step.kind, step.kind)}{duration}")
            if step.input != previous:
                with st.expander("Input dello step (dal template)"):
                    st.text(step.input)
            if step.output is not None:
                st.markdown(step.output)
            if step.error:
                st.error(step.error)
            if step.agent_run_id:
                st.caption(f"Run agente `{step.agent_run_id[:8]}…` · costi e trace in Admin → Observability")
        previous = step.output or ""

    if run.status == "queued":
        st.caption("In coda: parte appena il worker è libero.")
    _delete_run(run)


def _delete_run(run: PipelineRun) -> None:
    if run.status == "running":
        st.caption("In corso: si potrà eliminare quando è finita.")
        return
    with st.popover("🗑️ Elimina esecuzione"):
        st.write("Eliminare questa esecuzione dallo storico? Le run degli agenti restano in Observability.")
        if st.button("Sì, elimina", type="primary", key=f"run_delete_{run.id}"):
            try:
                api().automation.delete_run(run.id)
            except ApiError as exc:
                st.error(str(exc))
                return
            st.rerun(scope="fragment")


def _run_title(pipeline_name: str, run: PipelineRun) -> str:
    title = f"{_STATUS_ICONS.get(run.status, '')} {pipeline_name} · {run.created_at.astimezone():%Y-%m-%d %H:%M:%S}"
    if run.finished_at and run.started_at:
        title += f" · {_seconds(run.started_at, run.finished_at)}"
    return title


def _seconds(start, end) -> str:
    return f"{(end - start).total_seconds():.1f} s"


def _step_label(step: Step) -> str:
    if step.kind == "agent_config":
        return f"{step.name} (Libreria: `{step.agent_config_name}`)"
    if step.kind == "function":
        return f"{step.name} (funzione `{step.function_name}`)"
    return f"{step.name} (agente proprio)"


# ------------------------------------------------------------------- editor
# The step list lives in session_state while the dialog is open: ``<key>_order``
# holds one uid per step (in order) and each field is the widget key
# ``<key>_<uid>_<field>``, so steps can be added, moved and removed freely.

def _open_editor(project_name: str, pipeline: Pipeline | None) -> None:
    key = _editor_key(project_name, pipeline)
    for state_key in [k for k in st.session_state if str(k).startswith(f"{key}_")]:
        del st.session_state[state_key]
    st.session_state[f"{key}_order"] = []
    for step in pipeline.steps if pipeline else []:
        _add_step(key, step)
    _editor_dialog(project_name, pipeline)


@st.dialog("Automation", width="large")
def _editor_dialog(project_name: str, current: Pipeline | None) -> None:
    automation = api().automation
    key = _editor_key(project_name, current)
    name = st.text_input("Nome", value=current.name if current else "", key=f"{key}_name")
    description = st.text_input("Descrizione", value=current.description if current else "", key=f"{key}_description")
    active = st.toggle("Attiva", value=current.active if current else True, key=f"{key}_active")

    st.markdown("**Step**")
    st.caption(f"Ogni step riceve il proprio template: `{INPUT}` = output dello step prima "
               f"(input dell'esecuzione per il primo), `{PIPELINE_INPUT}` = input dell'esecuzione.")
    agents = {agent.name: agent for agent in api().agents.agents(project_name, include_global=True)}
    tools = [tool.name for tool in api().agents.tools() if tool.available]
    functions = {spec.name: spec for spec in automation.functions()}
    order = st.session_state[f"{key}_order"]
    for index, uid in enumerate(order):
        _step_editor(key, uid, index, len(order), agents, tools, functions)
    st.button("➕ Aggiungi step", key=f"{key}_add", on_click=_add_step, args=(key, None))

    st.divider()
    col_save, col_cancel, col_delete = st.columns([1, 1, 2], vertical_alignment="bottom")
    if col_save.button("Salva", type="primary", width="stretch", key=f"{key}_save"):
        try:
            steps = [_read_step(key, uid, functions) for uid in order]
            if current is None:
                created = automation.create_pipeline(project_name, name, description, active, steps)
                st.session_state[f"automation_{project_name}_select"] = created.id
            else:
                automation.update_pipeline(current.id, name, description, active, steps)
        except ApiError as exc:
            st.error(str(exc))
            return
        st.rerun()
    if col_cancel.button("Annulla", width="stretch", key=f"{key}_cancel"):
        st.rerun()
    if current is not None:
        with col_delete.popover("Elimina automation", width="stretch"):
            st.write(f"Eliminare **{current.name}** e il suo storico? Le run degli agenti restano.")
            if st.button("Sì, elimina", type="primary", key=f"{key}_delete"):
                automation.delete_pipeline(current.id)
                st.rerun()


def _step_editor(key: str, uid: str, index: int, count: int, agents: dict, tools: list[str],
                 functions: dict[str, Function]) -> None:
    field = f"{key}_{uid}"
    with st.container(border=True):
        col_title, col_up, col_down, col_remove = st.columns([6, 1, 1, 1], vertical_alignment="center")
        col_title.markdown(f"**{index + 1}. {st.session_state.get(f'{field}_name') or 'Nuovo step'}**")
        col_up.button("⬆", key=f"{field}_up", disabled=index == 0, on_click=_move, args=(key, index, -1), width="stretch")
        col_down.button("⬇", key=f"{field}_down", disabled=index == count - 1, on_click=_move, args=(key, index, 1),
                        width="stretch")
        col_remove.button("🗑", key=f"{field}_remove", on_click=_remove, args=(key, uid), width="stretch")

        col_name, col_kind = st.columns(2)
        col_name.text_input("Nome dello step", key=f"{field}_name")
        kind = col_kind.selectbox("Tipo", list(_KIND_LABELS), format_func=_KIND_LABELS.get, key=f"{field}_kind")
        st.text_area("Template dell'input", key=f"{field}_template", height=68)

        if kind == "agent":
            st.text_area("System prompt", key=f"{field}_prompt", height=120,
                         placeholder="Cosa fa questo step e come deve rispondere…")
            col_model, col_steps = st.columns([3, 1])
            model_select(col_model, st.session_state.get(f"{field}_model"), key=f"{field}_model")
            col_steps.number_input("Max steps", min_value=1, max_value=50, key=f"{field}_max_steps")
            st.multiselect("Tool", tools, key=f"{field}_tools")
        elif kind == "function":
            function_name = st.selectbox("Funzione", list(functions), key=f"{field}_function")
            spec = functions[function_name]
            st.caption(spec.description)
            _params_form(field, spec)
        elif not agents:
            st.info("Nessun agente nella Libreria o nel progetto.")
        else:
            st.selectbox(
                "Agente", list(agents), key=f"{field}_agent",
                format_func=lambda name: f"{name} ({'progetto' if agents[name].project_name else 'globale'})",
            )


def _params_form(field: str, spec: Function) -> None:
    """One widget per parameter of the function, by type. Widget keys include
    the function name, so switching function never mixes parameters."""
    saved_function, saved_params = st.session_state.get(f"{field}_saved_params", (None, {}))
    for param in spec.params:
        key = _param_key(field, spec, param.name)
        if key not in st.session_state:
            default = saved_params.get(param.name, param.default) if saved_function == spec.name else param.default
            st.session_state[key] = _typed(param.type, default)
        label = param.name.replace("_", " ").capitalize()
        if param.type == "bool":
            st.checkbox(label, key=key, help=param.description)
        elif param.type in ("int", "float"):
            st.number_input(label, key=key, help=param.description, step=1 if param.type == "int" else 0.1)
        else:
            st.text_input(label, key=key, help=param.description)


def _typed(kind: str, value):
    """``value`` as the widget of ``kind`` expects it (None → its empty value)."""
    if kind == "bool":
        return bool(value)
    if kind == "int":
        return int(value or 0)
    if kind == "float":
        return float(value or 0.0)
    return "" if value is None else str(value)


def _param_key(field: str, spec: Function, name: str) -> str:
    return f"{field}_param_{spec.name}_{name}"


def _add_step(key: str, step: Step | None) -> None:
    """Append a step to the editor: ``step`` from the API, or an empty own-agent step."""
    uid = uuid.uuid4().hex[:8]
    field = f"{key}_{uid}"
    agent = step.agent if step else None
    st.session_state[f"{field}_id"] = step.id if step else None
    st.session_state[f"{field}_name"] = step.name if step else ""
    st.session_state[f"{field}_kind"] = step.kind if step else "agent"
    st.session_state[f"{field}_template"] = step.input_template if step else INPUT
    st.session_state[f"{field}_prompt"] = agent.system_prompt if agent else ""
    st.session_state[f"{field}_model"] = agent.model if agent else next(iter(api().agents.model_choices().usable), None)
    st.session_state[f"{field}_max_steps"] = agent.max_steps if agent else 4
    st.session_state[f"{field}_tools"] = list(agent.tool_names) if agent else []
    if step and step.agent_config_name:
        st.session_state[f"{field}_agent"] = step.agent_config_name
    if step and step.function_name:
        st.session_state[f"{field}_function"] = step.function_name
        st.session_state[f"{field}_saved_params"] = (step.function_name, dict(step.params))
    st.session_state[f"{key}_order"].append(uid)


def _move(key: str, index: int, offset: int) -> None:
    order = st.session_state[f"{key}_order"]
    order[index], order[index + offset] = order[index + offset], order[index]


def _remove(key: str, uid: str) -> None:
    st.session_state[f"{key}_order"].remove(uid)


def _read_step(key: str, uid: str, functions: dict[str, Function]) -> Step:
    """The step as edited (validated by the API on save)."""
    field = f"{key}_{uid}"
    state = st.session_state
    kind = state[f"{field}_kind"]
    agent = None
    if kind == "agent":
        agent = StepAgent(
            system_prompt=state[f"{field}_prompt"], model=state[f"{field}_model"] or "",
            max_steps=int(state[f"{field}_max_steps"]), tool_names=list(state[f"{field}_tools"]),
        )
    function_name, params = None, {}
    if kind == "function":
        function_name = state[f"{field}_function"]
        spec = functions[function_name]
        params = {param.name: state[_param_key(field, spec, param.name)] for param in spec.params}
    return Step(
        id=state[f"{field}_id"],
        name=state[f"{field}_name"],
        kind=kind,
        input_template=state[f"{field}_template"],
        agent=agent,
        agent_config_name=state.get(f"{field}_agent") if kind == "agent_config" else None,
        function_name=function_name,
        params=params,
    )


def _editor_key(project_name: str, pipeline: Pipeline | None) -> str:
    return f"pipeline_form_{project_name}_{pipeline.id if pipeline else 'new'}"
