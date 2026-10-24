"""Masking section of a project's Impostazioni (rendered inside its expander):
the sensitive values the LLM sees as aliases. The tools add what they read
(e.g. repository names); here you add other values by hand or remove one."""
import pandas as pd
import streamlit as st

from api_client.client import ApiError
from views.services import api

_CATEGORIES = {"term": "Termine", "person": "Persona", "email": "Email", "repository": "Repository"}


def masking_section(project_name: str) -> None:
    key = f"masking_{project_name}"
    st.caption(
        "Valori che il modello non vede mai: al loro posto riceve un alias (es. `REPO_1`, `PERSONA_2`) e nella risposta "
        "l'alias torna il valore vero. I tool aggiungono da soli quello che leggono (es. i nomi dei repository); "
        "qui aggiungi altro a mano. Minimo 3 caratteri, maiuscole e minuscole indifferenti."
    )
    with st.form(f"{key}_form", clear_on_submit=True, border=False):
        col_category, col_value, col_add = st.columns([1, 3, 1], vertical_alignment="bottom")
        category = col_category.selectbox("Tipo", list(_CATEGORIES), format_func=_CATEGORIES.get, key=f"{key}_category")
        value = col_value.text_input("Valore da mascherare", placeholder="es. Banca delle banane", key=f"{key}_value")
        if col_add.form_submit_button("Aggiungi", type="primary", width="stretch"):
            try:
                entry = api().masking.add(project_name, category, value)
            except ApiError as exc:
                st.error(str(exc))
            else:
                st.toast(f"{entry.value} → {entry.alias}")

    entries = api().masking.entries(project_name)
    if not entries:
        st.caption("Nessun valore mascherato.")
        return
    rows = [{"alias": e.alias, "valore": e.value, "tipo": _CATEGORIES.get(e.category, e.category),
             "origine": "a mano" if e.manual else "tool"} for e in entries]
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    col_alias, col_remove = st.columns([3, 1], vertical_alignment="bottom")
    alias = col_alias.selectbox("Togli dal mascheramento", [e.alias for e in entries], key=f"{key}_remove_alias",
                                format_func=lambda a: f"{a} · {next(e.value for e in entries if e.alias == a)}")
    if col_remove.button("Togli", width="stretch", key=f"{key}_remove"):
        api().masking.remove(project_name, alias)
        st.rerun()
