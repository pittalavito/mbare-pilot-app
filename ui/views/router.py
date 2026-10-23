"""UI composition: the pages, all served through the API. The sidebar always
shows the backend panel (start/stop API and worker); while the API is down
the start screen replaces the pages."""
import streamlit as st

from api_client.client import ApiUnavailable
from views.admin_view import admin_page
from views.backend_panel import backend_sidebar, backend_start_screen
from views.library_view import library_page
from views.projects_view import projects_page
from views.services import api


def run_router() -> None:
    with st.sidebar:
        backend_sidebar()

    if not api().health():
        backend_start_screen()
        return

    pages = [
        st.Page(projects_page, title="Progetti", icon="📁", default=True),
        st.Page(library_page, title="Libreria", icon="📚", url_path="libreria"),
        st.Page(admin_page, title="Admin", icon="🛠️", url_path="admin"),
    ]
    try:
        st.navigation(pages).run()
    except ApiUnavailable as exc:  # the API went down while using the page
        st.error(str(exc))
