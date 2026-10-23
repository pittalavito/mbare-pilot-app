"""Library page: what every project can use. Global agents (with their roles
and prompts) and the tool catalog."""
import pandas as pd
import streamlit as st

from views.agents_view import agents_section
from views.services import api


def library_page() -> None:
    st.title("Libreria")
    st.caption(
        "Agenti e tool **globali**, usabili da tutti i progetti. Gli agenti di un solo progetto "
        "si gestiscono dalle sue **Impostazioni**. Ruoli e prompt non si cancellano: si disattivano."
    )
    tab_agents, tab_tools = st.tabs(["Agenti globali", "Tool"], key="library_tab")
    with tab_agents:
        agents_section(None)
    with tab_tools:
        _tools_tab()


def _tools_tab() -> None:
    tools = api().agents.tools()
    st.caption("I tool sono implementati nel codice (tool/) e registrati qui all'avvio.")
    if not tools:
        st.info("Nessun tool nel catalogo.")
        return
    rows = [
        {"tool": tool.name, "descrizione": tool.description, "disponibile": "✅" if tool.available else "❌"}
        for tool in tools
    ]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
