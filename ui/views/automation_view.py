"""Automation tab of a project: its automations (created and edited as a
graph in views/automation_editor.py), «Esegui» to queue a run for the worker,
and the run history, refreshed every few seconds while a run is queued or running."""
import streamlit as st

from api_client.client import ApiError
from api_client.models import Pipeline, PipelineRun, Step
from views.automation_editor import automation_editor, editing, open_editor
from views.services import api

INPUT = "{input}"
_KIND_LABELS = {
    "agent": "Agente proprio",
    "agent_config": "Agente della Libreria",
    "function": "Funzione (codice)",
}
_STATUS_ICONS = {"queued": "⏳", "running": "🔄", "done": "✅", "failed": "❌", "skipped": "⏭️"}
_REFRESH_SECONDS = 2


def automation_section(project_name: str) -> None:
    key = f"automation_{project_name}"
    pipelines = api().automation.pipelines(project_name)
    current = editing(project_name)
    if current is not None:
        automation_editor(project_name, next((p for p in pipelines if p.id == current), None))
        return
    if not pipelines:
        st.info("Nessuna automation: creane una disegnando il suo grafo di step (agenti e funzioni che si passano il risultato).")
        st.button("➕ Nuova automation", type="primary", key=f"{key}_first", on_click=open_editor, args=(project_name, None))
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
    col_new.button("➕ Nuova", width="stretch", key=f"{key}_new", on_click=open_editor, args=(project_name, None))
    col_edit.button("✏️ Modifica", width="stretch", key=f"{key}_edit", on_click=open_editor, args=(project_name, pipeline))

    if pipeline.description:
        st.caption(pipeline.description)
    st.caption(_summary(pipeline) or "Nessuno step: aggiungili con ✏️ Modifica.")
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
    _worker_status()


def _worker_status() -> None:
    """Who executes the queue: the running workers, or a warning when there is none."""
    workers = api().automation.workers()
    if not workers:
        st.warning("Nessun worker attivo: le esecuzioni restano in coda. "
                   "Avvialo dalla barra laterale (Backend → Worker automation).")
        return
    busy = [f"#{worker.busy_run_id}" for worker in workers if worker.busy_run_id is not None]
    activity = f"esegue {', '.join(busy)}" if busy else "libero"
    st.caption(f"🟢 {len(workers)} worker attivo{'i' if len(workers) > 1 else ''} · {activity}")


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


def _summary(pipeline: Pipeline) -> str:
    """The steps, and how many edges join them (branches have conditions)."""
    if not pipeline.steps:
        return ""
    conditional = sum(1 for edge in pipeline.edges if edge.condition != "always")
    branches = f" · {conditional} con condizione" if conditional else ""
    steps = " · ".join(_step_label(step) for step in pipeline.steps)
    return f"{len(pipeline.steps)} step, {len(pipeline.edges)} collegamenti{branches}: {steps}"


def _step_label(step: Step) -> str:
    if step.kind == "agent_config":
        return f"{step.name} (Libreria: `{step.agent_config_name}`)"
    if step.kind == "function":
        return f"{step.name} (funzione `{step.function_name}`)"
    return f"{step.name} (agente proprio)"
