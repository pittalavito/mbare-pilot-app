"""Model picker shared by the forms: the active models of the catalog, plus
the current one when it is no longer usable (from /models/choices)."""
import streamlit as st

from views.services import api


def model_select(container, current: str | None, key: str) -> str | None:
    """A selectbox of catalog model keys in ``container`` (``st`` or a column).
    Shows a warning under it when the selected model is no longer usable."""
    catalog = api().agents.model_choices(current)
    if not catalog.choices:
        container.warning("Nessun modello attivo: aggiungine uno in Admin → Modelli.")
        return None
    if key in st.session_state and st.session_state[key] not in catalog.choices:
        del st.session_state[key]
    # Preset in session_state: no index, or Streamlit warns.
    index = {} if key in st.session_state else {
        "index": catalog.choices.index(current) if current in catalog.choices else 0,
    }
    selected = container.selectbox(
        "Modello", catalog.choices, key=key, help="Dal catalogo in Admin → Modelli (formato fornitore/modello).", **index,
    )
    if selected not in catalog.usable:
        container.warning(f"{selected} non è più nel catalogo o è disattivato: scegline un altro.")
    return selected
