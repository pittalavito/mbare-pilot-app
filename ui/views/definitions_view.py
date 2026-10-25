"""Definitions as files, in a project's settings: agents, chatbots and
automations written as YAML in the data folder (``definition/``), applied to
the project with one button. The file wins over what was changed here; what is
not in the files stays."""
import streamlit as st

from api_client.client import ApiError
from views.services import api

_OUTCOMES = {
    "created": "✅ creato",
    "updated": "🔄 aggiornato",
    "unchanged": "➖ invariato",
    "error": "❌ errore",
}
_KINDS = {"agent": "Agente", "chatbot": "Chatbot", "automation": "Automation"}


def definitions_section(project_name: str) -> None:
    key = f"definitions_{project_name}"
    st.caption(
        "Nella cartella dei dati, `definition/`: `global-agent.yml` (agenti della Libreria), "
        "`global-chat-bot.yml` e `global-automation.yml` (base per ogni progetto) e "
        "`project/<progetto>/` con `agent.yml`, `chat-bot.yml`, `automation.yml`. Il pulsante crea o aggiorna "
        "quello che i file definiscono, cercandolo per nome: **il file vince** sulle modifiche fatte da qui. "
        "Quello che non è nei file resta com'è."
    )
    # A callback: the click is never lost to a rerun (see the automation editor).
    st.button("⟳ Sincronizza da file", type="primary", key=f"{key}_sync", on_click=_sync, args=(project_name, key))
    if error := st.session_state.get(f"{key}_error"):
        st.error(error)
    report = st.session_state.get(f"{key}_report")
    if report is None:
        return
    if not report.items:
        st.info("Nessun file di definizione nella cartella del progetto.")
        return
    for item in report.items:
        line = f"{_OUTCOMES.get(item.outcome, item.outcome)} · {_KINDS.get(item.kind, item.kind)} **{item.name or '?'}** · `{item.file}`"
        if item.outcome == "error":
            st.error(f"{line}\n\n{item.message}")
        else:
            st.markdown(line)


def _sync(project_name: str, key: str) -> None:
    st.session_state.pop(f"{key}_error", None)
    try:
        st.session_state[f"{key}_report"] = api().definitions.sync(project_name)
    except ApiError as exc:
        st.session_state[f"{key}_error"] = str(exc)
        st.session_state.pop(f"{key}_report", None)
