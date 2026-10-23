"""Admin page, one tab per area: services (app config with secrets masked +
links to the service dashboards), observability (agent runs and tool calls,
with the verbatim trace of a run) and the model catalog. Atlassian is
configured per project (project page → Impostazioni)."""
from datetime import datetime

import pandas as pd
import streamlit as st

from api_client.client import ApiError
from api_client.models import CatalogModel, RunSummary, ToolCall
from views.services import api, config

_PROVIDERS = ["openrouter", "openai", "ollama"]
_MODEL_COLUMNS = ["provider", "model", "input_per_1m", "output_per_1m", "active"]


def admin_page() -> None:
    st.title("Admin")
    tab_services, tab_observability, tab_models = st.tabs(["Servizi", "Observability", "Modelli"], key="admin_tab")
    with tab_services:
        _services_section()
    with tab_observability:
        _observability_section()
    with tab_models:
        _models_section()


# ------------------------------------------------------------------ servizi

def _services_section() -> None:
    st.caption(
        "Config dell'app e dashboard di servizio: le dashboard si aprono in una scheda dedicata. "
        f"Avvia i container con `python {config().script_start_docker}`."
    )
    backend = api().admin.config()

    with st.container(border=True):
        st.subheader("Config")
        st.caption("Tutta la configurazione del backend (dal `.env`), con i segreti mascherati.")
        with st.expander("Apri"):
            rows = [
                {"chiave": key, "valore": "—" if value in (None, "") else str(value)}
                for key, value in backend.settings.items()
            ]
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    _dashboard_card(
        "Redis Dashboard", backend.redis_dashboard_port,
        f"Redis via redis-commander su `:{backend.redis_dashboard_port}`.",
    )
    _dashboard_card(
        "SQL Dashboard", backend.postgres_dashboard_port,
        f"Postgres via Adminer su `:{backend.postgres_dashboard_port}`: server `postgres`, credenziali dal `.env`.",
    )


def _dashboard_card(title: str, port: int, description: str) -> None:
    with st.container(border=True):
        col_text, col_link = st.columns([4, 1], vertical_alignment="center")
        col_text.subheader(title)
        col_text.caption(description)
        col_link.link_button("Apri", _dashboard_url(port), width="stretch")


def _dashboard_url(port: int) -> str:
    """Same host the browser used to reach the app (localhost, LAN IP, ...)."""
    host = (st.context.headers.get("Host") or "localhost").rsplit(":", 1)[0]
    return f"http://{host}:{port}"


# ------------------------------------------------------------ observability

def _observability_section() -> None:
    if st.button("Aggiorna", key="refresh_runs"):
        st.rerun()

    tab_agents, tab_tools = st.tabs(["Agent Runs", "Tool Calls"], key="observability_tab")
    with tab_agents:
        runs = api().admin.runs()
        if not runs:
            st.info("Nessun agent run registrato.")
        else:
            st.dataframe(pd.DataFrame([_run_row(run) for run in runs]), width="stretch")
            run_id = st.selectbox("Dettaglio run", [run.run_id for run in runs], format_func=lambda rid: f"{rid[:8]}…")
            try:
                st.json(api().admin.trace(run_id))
            except ApiError:
                st.warning("Trace non trovato in Redis.")

    with tab_tools:
        tool_calls = api().admin.tool_calls()
        if not tool_calls:
            st.info("Nessuna tool call registrata.")
        else:
            st.dataframe(pd.DataFrame([_tool_call_row(call) for call in tool_calls]), width="stretch")


def _run_row(run: RunSummary) -> dict[str, object]:
    return {
        "run_id": run.run_id[:8] + "…",
        "project": run.project_name or "—",
        "origin": run.origin,
        "config": run.config_name,
        "role": run.role_name,
        "prompt": f"v{run.prompt_version}",
        "ok": "✅" if run.ok else "❌",
        "latency_ms": run.latency_ms,
        "model": run.model,
        "in_tok": run.total_tokens.input_tokens,
        "out_tok": run.total_tokens.output_tokens,
        "agent_cost_eur": run.agent_tokens.cost_eur,
        "tool_cost_eur": run.tool_tokens.cost_eur,
        "cost_eur": run.total_tokens.cost_eur,
        "tools_called": ", ".join(run.tool_names) or "—",
        "ts": _local_time(run.created_at),
    }


def _tool_call_row(call: ToolCall) -> dict[str, object]:
    return {
        "run_id": call.run_id[:8] + "…",
        "tool": call.tool_name,
        "ok": "✅" if call.ok else "❌",
        "latency_ms": call.latency_ms,
        "in_tok": call.tokens.input_tokens,
        "out_tok": call.tokens.output_tokens,
        "cost_eur": call.tokens.cost_eur,
        "ts": _local_time(call.created_at),
    }


def _local_time(value: datetime) -> str:
    """UTC timestamp -> local time of the machine running the UI."""
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------------ modelli

def _models_section() -> None:
    st.caption(
        "Il catalogo dei modelli usabili da agenti, chatbot e automation. **OpenRouter** è il fornitore principale: "
        "`model` è l'id del modello sul fornitore (es. `google/gemini-2.5-pro` su OpenRouter, `gpt-4o` su OpenAI, "
        "`mistral:7b` su Ollama). Prezzi in EUR per 1M token. Un modello in uso non si elimina: disattivalo."
    )
    table = pd.DataFrame([model.model_dump() for model in api().admin.models()], columns=[*_MODEL_COLUMNS, "in_use"])
    edited = st.data_editor(
        table,
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        key="models_editor",
        column_config={
            "provider": st.column_config.SelectboxColumn("Fornitore", options=_PROVIDERS, required=True),
            "model": st.column_config.TextColumn("Modello", required=True),
            "input_per_1m": st.column_config.NumberColumn("Input €/1M", min_value=0.0, format="%.2f", default=0.0),
            "output_per_1m": st.column_config.NumberColumn("Output €/1M", min_value=0.0, format="%.2f", default=0.0),
            "active": st.column_config.CheckboxColumn("Attivo", default=True),
            "in_use": st.column_config.CheckboxColumn("In uso", disabled=True),
        },
    )

    if not st.button("Salva", type="primary", key="models_save"):
        return
    rows = edited.dropna(how="all", subset=["provider", "model"]).to_dict(orient="records")
    try:
        models = [CatalogModel.model_validate({c: row[c] for c in _MODEL_COLUMNS if pd.notna(row[c])}) for row in rows]
        api().admin.save_models(models)
    except ApiError as exc:
        st.error(str(exc))
        return
    except ValueError as exc:  # a row the UI model rejects (pydantic ValidationError is a ValueError)
        st.error(f"Modello non valido: {exc}")
        return
    st.success("Catalogo salvato.")
    st.rerun()
