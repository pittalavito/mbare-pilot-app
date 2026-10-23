"""Git tab of a project: pick one of the repositories in the project folder,
then either search its commits (optional filters: author, message, commit
hash) or list its changed files. Git runs only on those two buttons; the
last result stays on screen across reruns."""
import pandas as pd
import streamlit as st

from api_client.client import ApiError
from api_client.models import Change, Commit, GitStatus
from views.services import api

_LIMITS = [25, 50, 100, 200]
_KIND_LABELS = {
    "modified": "modificato",
    "added": "aggiunto",
    "deleted": "eliminato",
    "renamed": "rinominato",
    "copied": "copiato",
    "type_changed": "tipo cambiato",
    "untracked": "nuovo (non tracciato)",
    "conflict": "in conflitto",
}


def git_section(project_name: str) -> None:
    key = f"git_{project_name}"
    try:
        repos = api().git.repositories(project_name)
    except ApiError as exc:
        st.error(str(exc))
        return
    if not repos:
        st.info("Nessun repository git nella cartella del progetto.")
        return

    with st.form(f"{key}_form", border=False):
        col_repo, col_limit = st.columns([4, 1], vertical_alignment="bottom")
        path = col_repo.selectbox(
            f"Repository ({len(repos)})", [repo.path for repo in repos], index=None,
            placeholder="Scegli un repository", format_func=_repo_label, key=f"{key}_repo",
        )
        limit = col_limit.selectbox("Commit", _LIMITS, index=1, key=f"{key}_limit")
        col_author, col_message, col_commit = st.columns([2, 3, 2])
        author = col_author.text_input("Autore", placeholder="nome o email", key=f"{key}_author")
        message = col_message.text_input("Messaggio contiene", key=f"{key}_message")
        commit = col_commit.text_input("Commit", placeholder="hash, anche abbreviato", key=f"{key}_commit")
        col_log, col_status, _ = st.columns([1, 1, 3])
        search_log = col_log.form_submit_button("Cerca commit", type="primary", width="stretch")
        check_status = col_status.form_submit_button("File modificati", width="stretch")

    result_key = f"{key}_result"
    if search_log or check_status:
        if path is None:
            st.warning("Scegli un repository.")
            return
        try:
            if search_log:
                result = api().git.log(project_name, path, limit=limit, author=author, message=message, commit=commit)
            else:
                result = api().git.status(project_name, path)
        except ApiError as exc:
            st.session_state.pop(result_key, None)
            st.error(str(exc))
            return
        st.session_state[result_key] = (path, result)

    if result_key not in st.session_state:
        return
    searched_path, result = st.session_state[result_key]
    if isinstance(result, GitStatus):
        _status_view(searched_path, result)
    else:
        _log_view(searched_path, result)


def _log_view(path: str, commits: list[Commit]) -> None:
    if not commits:
        st.info("Nessun commit con questi filtri.")
        return
    st.caption(f"{len(commits)} commit di `{_repo_label(path)}`")
    st.dataframe(pd.DataFrame([_commit_row(commit) for commit in commits]), width="stretch", hide_index=True)


def _status_view(path: str, status: GitStatus) -> None:
    branch = f"branch `{status.branch}`" if status.branch else "HEAD staccato (nessun branch)"
    sync = ""
    if status.upstream:
        sync = f" · `{status.upstream}`: {status.ahead} da pushare, {status.behind} da pullare"
    st.caption(f"`{_repo_label(path)}` · {branch}{sync}")
    if status.is_clean:
        st.success("Nessun file modificato.")
        return
    st.warning(f"{len(status.changes)} file modificati.")
    st.dataframe(pd.DataFrame([_change_row(change) for change in status.changes]), width="stretch", hide_index=True)


def _repo_label(path: str) -> str:
    return path or "(cartella del progetto)"


def _commit_row(commit: Commit) -> dict[str, str]:
    return {
        "data": f"{commit.date.astimezone():%Y-%m-%d %H:%M}",
        "commit": commit.short_hash,
        "autore": commit.author,
        "messaggio": commit.subject,
    }


def _change_row(change: Change) -> dict[str, str]:
    stage = "staged" if change.staged and not change.unstaged else "da aggiungere" if not change.staged else "in parte staged"
    return {
        "file": change.path + (f"  ← {change.original_path}" if change.original_path else ""),
        "modifica": _KIND_LABELS.get(change.kind, change.kind),
        "stato": stage,
    }
