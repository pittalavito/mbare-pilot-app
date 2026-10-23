"""Atlassian section of a project's Impostazioni (rendered inside its expander):
the project's Jira + Confluence site (URL, email, API token) and its default
Jira project / Confluence space. The saved token never comes back from the API."""
import streamlit as st

from api_client.client import ApiError
from views.services import api

_TOKEN_URL = "https://id.atlassian.com/manage-profile/security/api-tokens"


def atlassian_section(project_name: str) -> None:
    atlassian = api().atlassian
    settings = atlassian.settings(project_name)
    key = f"atlassian_{project_name}"

    with st.container():
        st.caption(f"Il sito Atlassian Cloud di questo progetto. Il token si crea su [id.atlassian.com]({_TOKEN_URL}).")

        base_url = st.text_input(
            "URL del sito", value=settings.base_url if settings else "",
            placeholder="https://acme.atlassian.net", key=f"{key}_url",
        )
        email = st.text_input("Email", value=settings.email if settings else "", key=f"{key}_email")
        api_token = st.text_input(
            "API token", type="password", key=f"{key}_token",
            placeholder="•••••••• (salvato: lascia vuoto per non cambiarlo)" if settings and settings.has_token else "",
        )
        col_jira, col_space = st.columns(2)
        jira_key = col_jira.text_input(
            "Progetto Jira (opzionale)", value=settings.jira_project_key if settings else "",
            placeholder="PROJ", key=f"{key}_jira",
        )
        space_key = col_space.text_input(
            "Spazio Confluence (opzionale)", value=settings.confluence_space_key if settings else "",
            placeholder="DOC", key=f"{key}_space",
        )

        col_save, col_check, col_remove = st.columns(3)
        if col_save.button("Salva", type="primary", width="stretch", key=f"{key}_save"):
            try:
                atlassian.save(project_name, {
                    "base_url": base_url, "email": email, "api_token": api_token,
                    "jira_project_key": jira_key, "confluence_space_key": space_key,
                })
            except ApiError as exc:
                st.error(str(exc))
            else:
                st.session_state.pop(f"{key}_token", None)
                st.rerun()

        if col_check.button("Verifica connessione", width="stretch", key=f"{key}_check", disabled=settings is None):
            try:
                user = atlassian.check(project_name)
            except ApiError as exc:
                st.error(str(exc))
            else:
                st.success(f"Connesso come **{user.display_name}**" + (f" ({user.email})" if user.email else ""))

        if col_remove.button("Rimuovi", width="stretch", key=f"{key}_remove", disabled=settings is None):
            atlassian.remove(project_name)
            for suffix in ("url", "email", "token", "jira", "space"):
                st.session_state.pop(f"{key}_{suffix}", None)
            st.rerun()
