"""Dati tab of a project: the project's own data, kept by the app apart from
its code: markdown notes written here and uploaded files. These are the
sources of the project's RAG index."""
import streamlit as st

from api_client.client import ApiError
from api_client.models import DataFile
from views.services import api


def project_data_section(project_name: str) -> None:
    tab_notes, tab_files = st.tabs(["📝 Note", "📎 File"], key=f"data_tab_{project_name}")
    with tab_notes:
        _notes(project_name)
    with tab_files:
        _files(project_name)


# -------------------------------------------------------------------- notes

def _notes(project_name: str) -> None:
    data = api().data
    notes = data.notes(project_name)
    selected_key = f"note_selected_{project_name}"
    names = [note.name for note in notes]
    if st.session_state.get(selected_key) not in names:
        st.session_state[selected_key] = names[0] if names else None
    selected = st.session_state[selected_key]

    col_list, col_editor = st.columns([1, 3])
    with col_list:
        if st.button("➕ Nuova nota", type="primary", width="stretch", key=f"note_new_{project_name}"):
            _new_note_dialog(project_name)
        if not notes:
            st.caption("Nessuna nota.")
        for note in notes:
            st.button(
                note.name, key=f"note_pick_{project_name}_{note.name}", width="stretch",
                type="secondary" if note.name != selected else "tertiary",
                on_click=lambda name=note.name: st.session_state.update({selected_key: name}),
            )

    with col_editor:
        if selected is None:
            st.info("Le note sono file markdown del progetto: appunti, decisioni, contesto per gli agenti.")
            return
        text = st.text_area(
            selected, value=data.read_note(project_name, selected), height=400,
            key=f"note_text_{project_name}_{selected}",
        )
        col_save, col_preview, col_delete = st.columns([1, 1, 1])
        if col_save.button("Salva", type="primary", width="stretch", key=f"note_save_{project_name}_{selected}"):
            data.save_note(project_name, selected, text)
            st.toast(f"{selected} salvata.")
        with col_preview.popover("Anteprima", width="stretch"):
            st.markdown(text)
        with col_delete.popover("Elimina", width="stretch"):
            st.write(f"Eliminare **{selected}**?")
            if st.button("Sì, elimina", type="primary", key=f"note_delete_{project_name}_{selected}"):
                data.delete_note(project_name, selected)
                st.session_state[selected_key] = None
                st.rerun()


@st.dialog("Nuova nota")
def _new_note_dialog(project_name: str) -> None:
    name = st.text_input("Nome", placeholder="es. decisioni-architettura", key=f"note_new_name_{project_name}")
    if st.button("Crea", type="primary", key=f"note_new_save_{project_name}"):
        if not name.strip():
            st.error("Il nome è obbligatorio.")
            return
        data = api().data
        try:
            existing = {note.name.lower() for note in data.notes(project_name)}
            candidate = name.strip() if name.strip().lower().endswith(".md") else f"{name.strip()}.md"
            if candidate.lower() in existing:
                st.error(f"Esiste già una nota {candidate}.")
                return
            note = data.save_note(project_name, name, f"# {name.strip()}\n")
        except ApiError as exc:
            st.error(str(exc))
            return
        st.session_state[f"note_selected_{project_name}"] = note.name
        st.session_state.pop(f"note_new_name_{project_name}", None)
        st.rerun()


# -------------------------------------------------------------------- files

def _files(project_name: str) -> None:
    data = api().data
    counter_key = f"upload_counter_{project_name}"
    counter = st.session_state.setdefault(counter_key, 0)

    uploads = st.file_uploader(
        "Carica documenti", accept_multiple_files=True, key=f"upload_{project_name}_{counter}",
        help="Un file con lo stesso nome viene sovrascritto.",
    )
    if uploads and st.button(f"Salva {len(uploads)} file", type="primary", key=f"upload_save_{project_name}"):
        try:
            for upload in uploads:
                data.save_file(project_name, upload.name, upload.getvalue())
        except ApiError as exc:
            st.error(str(exc))
            return
        st.session_state[counter_key] = counter + 1  # new key = empty uploader
        st.rerun()

    files = data.files(project_name)
    st.caption(f"{len(files)} file")
    for item in files:
        _file_row(project_name, item)


def _file_row(project_name: str, item: DataFile) -> None:
    with st.container(border=True):
        col_name, col_download, col_delete = st.columns([4, 1, 1], vertical_alignment="center")
        col_name.markdown(f"**{item.name}**")
        col_name.caption(f"{_size(item.size)} · {item.modified_at.astimezone():%d/%m/%Y %H:%M}")
        col_download.download_button(
            "Scarica", data=lambda: api().data.read_file(project_name, item.name),
            file_name=item.name, key=f"file_download_{project_name}_{item.name}", width="stretch",
        )
        with col_delete.popover("Elimina", width="stretch"):
            st.write(f"Eliminare **{item.name}**?")
            if st.button("Sì, elimina", type="primary", key=f"file_delete_{project_name}_{item.name}"):
                api().data.delete_file(project_name, item.name)
                st.rerun()


def _size(size: float) -> str:
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{size:.0f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"
