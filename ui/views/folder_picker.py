"""In-app folder browser over the API (/folders), confined to the backend's
PROJECT_ROOTS. Navigation reruns only the dialog it lives in."""
import streamlit as st

from api_client.client import ApiError
from views.services import api


def folder_picker(key: str, label: str) -> str:
    """The folder currently selected (absolute path, as the backend sees it)."""
    projects = api().projects
    cwd_key, input_key, error_key = f"{key}_cwd", f"{key}_input", f"{key}_error"
    if cwd_key not in st.session_state:
        st.session_state[cwd_key] = projects.list_folder().path
        st.session_state[input_key] = st.session_state[cwd_key]

    def go_to(path: str) -> None:
        st.session_state[cwd_key] = path
        st.session_state[input_key] = path
        st.session_state.pop(error_key, None)

    def go_to_typed() -> None:
        try:
            go_to(projects.list_folder(st.session_state[input_key]).path)
        except ApiError as exc:
            st.session_state[error_key] = str(exc)

    st.markdown(f"**{label}**")
    roots = projects.folder_roots()
    if len(roots) > 1:
        st.selectbox("Radice", roots, key=f"{key}_root", on_change=lambda: go_to(st.session_state[f"{key}_root"]))
    col_path, col_go = st.columns([5, 1], vertical_alignment="bottom")
    col_path.text_input("Percorso", key=input_key, on_change=go_to_typed)
    col_go.button("Vai", key=f"{key}_go", on_click=go_to_typed, width="stretch")
    if st.session_state.get(error_key):
        st.error(st.session_state[error_key])

    show_hidden = st.session_state.get(f"{key}_hidden", False)
    listing = projects.list_folder(st.session_state[cwd_key], show_hidden=show_hidden)
    col_up, col_hidden = st.columns([1, 2], vertical_alignment="center")
    col_up.button("⬆ Su", key=f"{key}_up", disabled=listing.parent is None,
                  on_click=go_to, args=(listing.parent,), width="stretch")
    col_hidden.checkbox("Mostra cartelle nascoste", key=f"{key}_hidden")

    with st.container(height=220, border=True):
        if not listing.subfolders:
            st.caption("Nessuna sottocartella.")
        for index, child in enumerate(listing.subfolders):
            st.button(f"📁 {child.name}", key=f"{key}_sub_{index}", on_click=go_to, args=(child.path,), width="stretch")
    st.caption(f"Selezionata: `{listing.path}`")
    return listing.path
