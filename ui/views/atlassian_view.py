"""Atlassian in a project: the settings section of Impostazioni (site URL,
email, API token, default Jira project / Confluence space; the saved token
never comes back from the API) and the Atlassian tab, shown only when the site
is configured: a Jira issue by key, the Confluence pages, and the project's
favorite issues and pages (saved in the app). Atlassian is called only on the
buttons; the last results stay on screen across reruns."""
import streamlit as st

from api_client.client import ApiError
from api_client.models import AtlassianSettings, ConfluencePage, Favorite, JiraIssue
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


# ---------------------------------------------------------------------- tab

_JIRA_ISSUE = "jira_issue"
_CONFLUENCE_PAGE = "confluence_page"


def is_configured(settings: AtlassianSettings | None) -> bool:
    return bool(settings and settings.base_url and settings.email and settings.has_token)


def atlassian_tab(project_name: str, settings: AtlassianSettings) -> None:
    st.caption(f"Sito `{settings.base_url}` · configurazione in 🔧 Impostazioni → Atlassian.")
    favorites = api().atlassian.favorites(project_name)
    tab_jira, tab_confluence = st.tabs(["Jira", "Confluence"], key=f"atlassian_tab_{project_name}")
    with tab_jira:
        _jira(project_name, settings, [f for f in favorites if f.kind == _JIRA_ISSUE])
    with tab_confluence:
        _confluence(project_name, settings, [f for f in favorites if f.kind == _CONFLUENCE_PAGE])


# --------------------------------------------------------------------- Jira

def _jira(project_name: str, settings: AtlassianSettings, favorites: list[Favorite]) -> None:
    key = f"jira_{project_name}"

    def open_issue(issue_key: str) -> None:
        _load(f"{key}_issue", lambda: api().atlassian.issue(project_name, issue_key))

    col_side, col_issue = st.columns([1, 2], gap="medium")
    with col_side:
        with st.form(f"{key}_form", border=False):
            placeholder = f"{settings.jira_project_key}-123" if settings.jira_project_key else "PROJ-123"
            issue_key = st.text_input("Chiave della issue", placeholder=placeholder, key=f"{key}_key")
            if st.form_submit_button("Cerca", type="primary", width="stretch"):
                if issue_key.strip():
                    open_issue(issue_key)
                else:
                    st.warning("Scrivi la chiave della issue.")
        _favorite_list(project_name, favorites, key, open_issue)
    with col_issue:
        issue = st.session_state.get(f"{key}_issue")
        if issue is None:
            st.info("Cerca una issue per chiave o aprila dai preferiti.")
        else:
            _issue_card(project_name, issue, favorites)


def _issue_card(project_name: str, issue: JiraIssue, favorites: list[Favorite]) -> None:
    with st.container(border=True):
        col_title, col_star = st.columns([5, 1], vertical_alignment="center")
        col_title.markdown(f"#### [{issue.key}]({issue.url}) · {issue.summary}")
        _star(col_star, project_name, favorites, _JIRA_ISSUE, issue.key, issue.summary, issue.url)
        facts = [
            ("Stato", issue.status), ("Tipo", issue.issue_type), ("Priorità", issue.priority),
            ("Assegnata a", issue.assignee or "nessuno"),
            ("Aggiornata", f"{issue.updated.astimezone():%d/%m/%Y %H:%M}" if issue.updated else None),
        ]
        st.caption(" · ".join(f"{label}: **{value}**" for label, value in facts if value))
        if issue.description:
            st.text(issue.description)
        else:
            st.caption("Nessuna descrizione.")


# --------------------------------------------------------------- Confluence

def _confluence(project_name: str, settings: AtlassianSettings, favorites: list[Favorite]) -> None:
    key = f"confluence_{project_name}"

    def open_page(page_id: str) -> None:
        _load(f"{key}_page", lambda: api().atlassian.page(project_name, page_id))

    col_list, col_page = st.columns([1, 2], gap="medium")
    with col_list:
        _favorite_list(project_name, favorites, key, open_page)
        if settings.confluence_space_key:
            if st.button(f"📄 Pagine dello spazio {settings.confluence_space_key}", width="stretch", key=f"{key}_load"):
                _load(f"{key}_pages", lambda: [(page.id, page.title) for page in api().atlassian.pages(project_name)])
        else:
            st.caption("Nessuno spazio predefinito: imposta lo spazio Confluence in Impostazioni per vederne le pagine.")
        with st.form(f"{key}_search_form", border=False):
            text = st.text_input("Cerca nelle pagine", key=f"{key}_text")
            if st.form_submit_button("Cerca", width="stretch"):
                if text.strip():
                    _load(f"{key}_pages", lambda: [(hit.id, hit.title) for hit in api().atlassian.search_pages(project_name, text)])
                else:
                    st.warning("Scrivi cosa cercare.")
        pages = st.session_state.get(f"{key}_pages")
        if pages is not None:
            st.caption(f"{len(pages)} pagine")
            for page_id, title in pages:
                if st.button(title, key=f"{key}_open_{page_id}", width="stretch"):
                    open_page(page_id)
    with col_page:
        page = st.session_state.get(f"{key}_page")
        if page is None:
            st.info("Apri una pagina dai preferiti o dall'elenco a sinistra.")
        else:
            _page_view(project_name, page, favorites)


def _page_view(project_name: str, page: ConfluencePage, favorites: list[Favorite]) -> None:
    with st.container(border=True):
        col_title, col_star = st.columns([5, 1], vertical_alignment="center")
        col_title.markdown(f"#### [{page.title}]({page.url})")
        _star(col_star, project_name, favorites, _CONFLUENCE_PAGE, page.id, page.title, page.url)
        if page.body:
            st.text(page.body)
        else:
            st.caption("Pagina vuota.")


# ---------------------------------------------------------------- favorites

def _favorite_list(project_name: str, favorites: list[Favorite], key: str, open_ref) -> None:
    """The favorites of one kind: click to open, 🗑 to remove."""
    st.markdown("**⭐ Preferiti**")
    if not favorites:
        st.caption("Nessun preferito: aprine uno e premi ☆.")
    for favorite in favorites:
        label = f"{favorite.ref} · {favorite.title}" if favorite.kind == _JIRA_ISSUE else favorite.title
        col_open, col_remove = st.columns([5, 1], vertical_alignment="center")
        if col_open.button(label, key=f"{key}_fav_{favorite.id}", width="stretch"):
            open_ref(favorite.ref)
        if col_remove.button("🗑", key=f"{key}_fav_remove_{favorite.id}", help="Togli dai preferiti", width="stretch"):
            _favorite_action(lambda favorite_id=favorite.id: api().atlassian.remove_favorite(project_name, favorite_id))
    st.divider()


def _star(container, project_name: str, favorites: list[Favorite], kind: str, ref: str, title: str, url: str) -> None:
    """☆ adds the issue or page to the favorites, ★ removes it."""
    saved = next((favorite for favorite in favorites if favorite.ref == ref), None)
    if saved is None:
        if container.button("☆", key=f"star_{kind}_{ref}", help="Aggiungi ai preferiti", width="stretch"):
            _favorite_action(lambda: api().atlassian.add_favorite(project_name, kind, ref, title, url))
    elif container.button("★", key=f"star_{kind}_{ref}", help="Togli dai preferiti", width="stretch"):
        _favorite_action(lambda: api().atlassian.remove_favorite(project_name, saved.id))


def _favorite_action(call) -> None:
    try:
        call()
    except ApiError as exc:
        st.error(str(exc))
        return
    st.rerun()


def _load(state_key: str, fetch) -> None:
    """Call Atlassian and keep the result under ``state_key``; show the error otherwise."""
    try:
        st.session_state[state_key] = fetch()
    except ApiError as exc:
        st.error(str(exc))
