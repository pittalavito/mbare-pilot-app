"""Projects page, the app's home. Without ``?p=`` it lists the projects (open
an existing folder / create one from scratch); with ``?p=<name>`` it shows one
project. Everything goes through the API."""
from pathlib import PurePosixPath, PureWindowsPath

import streamlit as st

from api_client.client import ApiError
from api_client.models import Project
from views.agents_view import agents_section
from views.atlassian_view import atlassian_section, atlassian_tab, is_configured
from views.automation_view import automation_section
from views.chat_view import chat_section
from views.folder_picker import folder_picker
from views.git_view import git_section
from views.project_data_view import project_data_section
from views.services import api

_PARAM = "p"
_TAGS = {"folder": "📂 Cartella esistente", "scratch": "✨ Creato da zero"}


def projects_page() -> None:
    name = st.query_params.get(_PARAM)
    if name:
        _project_detail(name)
    else:
        _project_list()


def _open_project(name: str | None) -> None:
    if name:
        st.query_params[_PARAM] = name
    else:
        st.query_params.pop(_PARAM, None)
    st.rerun()


# --------------------------------------------------------------- home: list

def _project_list() -> None:
    st.title("Progetti")
    col_folder, col_scratch, _ = st.columns([1, 1, 2])
    if col_folder.button("📂 Apri cartella", type="primary", width="stretch", key="project_new_folder"):
        _open_folder_dialog()
    if col_scratch.button("✨ Crea da zero", width="stretch", key="project_new_scratch"):
        _create_from_scratch_dialog()

    projects = api().projects.all()
    if not projects:
        st.info("Nessun progetto: apri una cartella che esiste già oppure creane uno da zero.")
        return
    for project in projects:
        _project_card(project)


def _project_card(project: Project) -> None:
    with st.container(border=True):
        col_info, col_open = st.columns([5, 1], vertical_alignment="center")
        col_info.markdown(f"#### {project.name}")
        if project.description:
            col_info.write(project.description)
        col_info.caption(f"{_TAGS.get(project.source, project.source)} · `{project.root_path}`")
        if not project.folder_exists:
            col_info.warning("La cartella non esiste più sul disco.")
        if col_open.button("Apri →", key=f"project_open_{project.name}", width="stretch"):
            _open_project(project.name)


# ----------------------------------------------------------- project detail

def _project_detail(name: str) -> None:
    try:
        project = api().projects.get(name)
    except ApiError as exc:
        st.error(str(exc))
        if st.button("← Progetti"):
            _open_project(None)
        return

    if st.button("← Progetti", key="project_back"):
        _open_project(None)
    st.title(project.name)
    st.caption(f"{_TAGS.get(project.source, project.source)} · `{project.root_path}`")
    if not project.folder_exists:
        st.warning("La cartella del progetto non esiste più sul disco.")

    atlassian = api().atlassian.settings(project.name)
    labels = ["💬 Chat", "⚙️ Automation", "🗂️ Dati", "🌿 Git"]
    if is_configured(atlassian):  # the tab exists only for a configured site
        labels.append("🔷 Atlassian")
    tabs = st.tabs([*labels, "🔧 Impostazioni"], key=f"project_tabs_{project.name}")
    tab_chat, tab_automation, tab_data, tab_git, tab_settings = *tabs[:4], tabs[-1]
    if is_configured(atlassian):
        with tabs[4]:
            atlassian_tab(project.name, atlassian)
    with tab_chat:
        chat_section(project.name)
    with tab_automation:
        automation_section(project.name)
    with tab_data:
        project_data_section(project.name)
    with tab_git:
        git_section(project.name)
    with tab_settings:
        _settings_tab(project)


def _settings_tab(project: Project) -> None:
    """One collapsed expander per section: only the titles show at first."""
    key = f"settings_{project.name}"
    with st.expander("Generale", key=f"{key}_general_open"):
        description = st.text_area("Descrizione", value=project.description, key=f"{key}_description")
        models = api().projects.embedding_models()
        embedding_model = st.selectbox(
            "Modello di embedding (RAG)", models,
            index=models.index(project.embedding_model) if project.embedding_model in models else 0,
            help="Usato per indicizzare i dati del progetto. Cambiarlo richiederà di reindicizzare.",
            key=f"{key}_embedding",
        )
        if st.button("Salva", type="primary", key=f"{key}_save"):
            try:
                api().projects.update(project.name, description, embedding_model)
            except ApiError as exc:
                st.error(str(exc))
                return
            st.success("Impostazioni salvate.")
            st.rerun()

    with st.expander("Atlassian (Jira + Confluence)", key=f"{key}_atlassian_open"):
        atlassian_section(project.name)

    with st.expander("Agenti del progetto", key=f"{key}_agents_open"):
        agents_section(project.name)

    with st.expander("🗑️ Rimuovi progetto", key=f"{key}_remove_open"):
        st.write(
            f"Rimuovere **{project.name}**? Spariscono dal DB i suoi agenti, chatbot, pipeline, indice RAG e config Atlassian. "
            "La cartella sul disco **non** viene toccata."
        )
        if st.button("Sì, rimuovi", type="primary", key=f"{key}_remove"):
            try:
                api().projects.remove(project.name)
            except ApiError as exc:
                st.error(str(exc))
                return
            _open_project(None)


# ------------------------------------------------------------------ dialogs

@st.dialog("Apri cartella", width="large")
def _open_folder_dialog() -> None:
    folder = folder_picker("pick_folder", label="Cartella del progetto")
    name = st.text_input("Nome", placeholder=_folder_name(folder), help="Vuoto = nome della cartella.",
                         key="pick_folder_name")
    description = st.text_area("Descrizione", key="pick_folder_description")

    if _save_buttons("pick_folder", "Apri come progetto"):
        _submit(
            lambda: api().projects.open_folder(folder, name.strip(), description.strip()),
            reset_keys=("pick_folder_name", "pick_folder_description"),
        )


@st.dialog("Crea da zero", width="large")
def _create_from_scratch_dialog() -> None:
    name = st.text_input("Nome", key="scratch_name")
    description = st.text_area("Descrizione", key="scratch_description")
    parent = folder_picker("scratch_parent", label="Dove crearlo")
    folder_name = st.text_input(
        "Nome della cartella", placeholder=name.strip() or "nuovo-progetto",
        help="Vuoto = nome del progetto.", key="scratch_folder_name",
    )
    final_name = folder_name.strip() or name.strip()
    if final_name:
        st.caption("Verrà creata:")
        st.code(_join(parent, final_name), language=None)

    if _save_buttons("scratch", "Crea progetto"):
        _submit(
            lambda: api().projects.create_from_scratch(name.strip(), parent, final_name, description.strip()),
            reset_keys=("scratch_name", "scratch_description", "scratch_folder_name"),
        )


def _save_buttons(key: str, label: str) -> bool:
    st.divider()
    col_save, col_cancel = st.columns(2)
    if col_cancel.button("Annulla", width="stretch", key=f"{key}_cancel"):
        st.rerun()
    return col_save.button(label, type="primary", width="stretch", key=f"{key}_save")


def _submit(action, reset_keys: tuple[str, ...]) -> None:
    """Run a create call; show the API error inside the dialog, or clear the
    form fields and close it (the picker keeps its last folder)."""
    try:
        action()
    except ApiError as exc:
        st.error(str(exc))
        return
    for key in reset_keys:
        st.session_state.pop(key, None)
    st.rerun()


def _folder_name(path: str) -> str:
    """Last segment of a backend path (Windows or POSIX)."""
    return (PureWindowsPath(path) if "\\" in path else PurePosixPath(path)).name


def _join(parent: str, name: str) -> str:
    return str((PureWindowsPath(parent) if "\\" in parent else PurePosixPath(parent)) / name)
