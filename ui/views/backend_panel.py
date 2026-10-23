"""Backend controls: start/stop the API and the automation worker from the UI,
with their status and the tail of their log. Processes run on this PC and
keep running when the page reloads or the UI restarts."""
import time

import streamlit as st

from process_control.manager import ManagedService, ServiceStatus
from process_control.services import backend_services, process_manager
from views.services import config

_STATUS_LABELS = {
    ServiceStatus.RUNNING: "🟢 attivo",
    ServiceStatus.STARTING: "🟡 in avvio",
    ServiceStatus.STOPPED: "⚪ spento",
    ServiceStatus.EXTERNAL: "🟢 attivo (avviato da terminale)",
}
_API_START_TIMEOUT = 30


def _services() -> dict[str, ManagedService]:
    return {service.name: service for service in backend_services(config().api_url)}


def backend_sidebar() -> None:
    """Compact panel for the sidebar: one row per backend process."""
    st.markdown("**Backend**")
    manager = process_manager()
    for service in _services().values():
        status = manager.status(service)
        col_label, col_action = st.columns([3, 2], vertical_alignment="center")
        col_label.caption(f"{service.label}  \n{_STATUS_LABELS[status]}")
        _action_button(col_action, service, status)
    with st.expander("Log"):
        for service in _services().values():
            st.caption(service.label)
            st.code(manager.logs(service, lines=15) or "(vuoto)", language=None)


def backend_start_screen() -> None:
    """Shown instead of the pages when the API is down."""
    st.title("Backend spento")
    st.write(f"La UI non raggiunge l'API su `{config().api_url}`.")
    services = _services()
    manager = process_manager()
    api_service = services["api"]
    status = manager.status(api_service)
    if status is ServiceStatus.STARTING:
        st.info("L'API si sta avviando…")
        _wait_for_api(api_service)
    if st.button("▶ Avvia il backend (API)", type="primary", key="backend_start_screen_api"):
        _start(api_service, wait=True)
    log = manager.logs(api_service, lines=30)
    if log:
        with st.expander("Ultimo log dell'API"):
            st.code(log, language=None)
    st.caption("In alternativa da terminale: `python resource/scripts/3-run-api.py`.")


def _action_button(container, service: ManagedService, status: ServiceStatus) -> None:
    if status is ServiceStatus.EXTERNAL:
        container.button("⏹", key=f"backend_stop_{service.name}", disabled=True, width="stretch",
                         help="Avviato da terminale: fermalo da lì.")
    elif status is ServiceStatus.STOPPED:
        if container.button("▶", key=f"backend_start_{service.name}", width="stretch", help=f"Avvia {service.label}"):
            _start(service, wait=service.health_url is not None)
    elif container.button("⏹", key=f"backend_stop_{service.name}", width="stretch", help=f"Ferma {service.label}"):
        process_manager().stop(service)
        st.rerun()


def _start(service: ManagedService, wait: bool) -> None:
    try:
        process_manager().start(service)
    except (RuntimeError, OSError) as exc:
        st.error(str(exc))
        return
    if wait:
        _wait_for_api(service)
    st.rerun()


def _wait_for_api(service: ManagedService) -> None:
    """Poll until the service is healthy (or stopped / timed out), then rerun."""
    manager = process_manager()
    with st.spinner(f"Avvio di {service.label}…"):
        deadline = time.monotonic() + _API_START_TIMEOUT
        while time.monotonic() < deadline:
            status = manager.status(service)
            if status in (ServiceStatus.RUNNING, ServiceStatus.EXTERNAL):
                st.rerun()
            if status is ServiceStatus.STOPPED:
                st.error(f"{service.label} si è fermata subito: guarda il log qui sotto.")
                return
            time.sleep(0.5)
    st.warning(f"{service.label} non risponde ancora: guarda il log.")
