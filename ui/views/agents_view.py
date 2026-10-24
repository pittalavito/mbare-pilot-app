"""Agents section, reused with a scope: global agents in the Library page
(``scope`` None), a project's own agents in its settings (``scope`` = project
name). Tabs: agents (list + create/edit dialogs), versioned system prompts, roles.
Every rule (scope, activation, validation) is the backend's: errors come back
as API messages."""
import pandas as pd
import streamlit as st

from api_client.client import ApiError
from api_client.models import Agent, Role
from views.model_picker import model_select
from views.services import api


def agents_section(scope: str | None) -> None:
    tab_agents, tab_prompts, tab_roles = st.tabs(
        ["Agenti", "System prompt", "Ruoli"], key=f"agents_tab_{_key(scope)}",
    )
    with tab_agents:
        _agents_tab(scope)
    with tab_prompts:
        _prompts_tab(scope)
    with tab_roles:
        _roles_tab(scope)


def _key(scope: str | None) -> str:
    return scope or "global"


# ---------------------------------------------------------------- agents tab

def _agents_tab(scope: str | None) -> None:
    agents = api().agents.agents(scope)

    if st.button("➕ Crea nuovo agente", type="primary", key=f"agent_new_{_key(scope)}"):
        _create_dialog(scope)
    st.caption(f"{len(agents)} agenti configurati")

    if not agents:
        st.info("Nessun agente: crea il primo con «Crea nuovo agente».")
    for agent in agents:
        _agent_card(agent)
    if scope is not None:
        st.caption("Gli agenti globali (pagina **Libreria**) sono usabili anche in questo progetto.")


def _agent_card(agent: Agent) -> None:
    with st.container(border=True):
        blocked = agent.blocked_reason
        st.markdown(f"#### {agent.name}")
        st.markdown(f":orange[⏸️ Bloccato — {blocked}]" if blocked else ":green[✅ Eseguibile]")
        if agent.description:
            st.write(agent.description)
        st.caption(
            f"Ruolo `{agent.role_name}` · Prompt `v{agent.prompt_version or '?'}` · "
            f"Modello `{agent.model}` · Max steps `{agent.max_steps}`"
        )
        st.caption("Tool: " + (", ".join(f"`{name}`" for name in agent.tool_names) or "nessuno"))
        if st.button("✏️ Modifica", key=f"agent_edit_{agent.name}"):
            _edit_dialog(agent.name)


@st.dialog("Nuovo agente", width="large")
def _create_dialog(scope: str | None) -> None:
    _agent_form(None, scope)


@st.dialog("Modifica agente", width="large")
def _edit_dialog(name: str) -> None:
    agent = api().agents.agent(name)
    _agent_form(agent, agent.project_name)


def _agent_form(current: Agent | None, scope: str | None) -> None:
    """Create (``current`` None) or edit form, shown inside a dialog. Saving or
    deleting reruns the page, which closes the dialog. A project agent may use
    global roles or the project's own."""
    agents_api = api().agents
    key = f"agent_form_{_key(scope)}_{current.name if current else 'new'}"

    roles = agents_api.roles(scope, include_global=scope is not None)
    role_names = [role.name for role in roles if role.active or (current and role.name == current.role_name)]
    if not role_names:
        st.info("Nessun ruolo attivo: creane o riattivane uno nel tab Ruoli.")
        return

    name = st.text_input(
        "Nome", value=current.name if current else "", disabled=current is not None,
        help="Identificativo dell'agente, non modificabile dopo la creazione.", key=f"{key}_name",
    )
    description = st.text_input("Descrizione", value=current.description if current else "", key=f"{key}_description")

    col_role, col_prompt = st.columns(2)
    role_name = col_role.selectbox(
        "Ruolo", role_names,
        index=role_names.index(current.role_name) if current and current.role_name in role_names else 0,
        format_func=lambda role: role if _is_active_role(roles, role) else f"{role} (disattivato)",
        key=f"{key}_role",
    )
    prompts = [
        prompt for prompt in agents_api.prompts(role_name)
        if prompt.active or (current and prompt.id == current.prompt_id)
    ]
    if not prompts:
        st.warning(f"Il ruolo {role_name} non ha versioni del prompt attive: creane una nel tab System prompt.")
        return
    prompt_by_id = {prompt.id: prompt for prompt in prompts}
    prompt_ids = list(prompt_by_id)
    prompt_id = col_prompt.selectbox(
        "Versione del system prompt", prompt_ids,
        index=prompt_ids.index(current.prompt_id) if current and current.prompt_id in prompt_ids else 0,
        format_func=lambda pid: f"v{prompt_by_id[pid].version}" + ("" if prompt_by_id[pid].active else " (disattivata)"),
        key=f"{key}_prompt_{role_name}",
    )
    with st.expander("Testo del prompt selezionato"):
        st.text(prompt_by_id[prompt_id].text)
    if not _is_active_role(roles, role_name):
        st.warning(f"Il ruolo {role_name} è disattivato: riattivalo nel tab Ruoli per poter salvare.")
    if not prompt_by_id[prompt_id].active:
        st.warning("Questa versione del prompt è disattivata: scegline una attiva o riattivala nel tab System prompt.")

    col_model, col_steps = st.columns(2)
    model = model_select(col_model, current.model if current else None, key=f"{key}_model")
    max_steps = col_steps.number_input(
        "Max steps", min_value=1, max_value=50, value=current.max_steps if current else 4, key=f"{key}_steps",
    )

    usable = [tool.name for tool in agents_api.tools() if tool.available and not tool.chatbot_only]
    saved_tools = current.tool_names if current else []
    tool_names = st.multiselect("Tool", usable, default=[n for n in saved_tools if n in usable], key=f"{key}_tools")
    missing = [n for n in saved_tools if n not in usable]
    if missing:
        st.warning(f"Tool non più disponibili, verranno rimossi al salvataggio: {', '.join(missing)}")

    st.divider()
    col_save, col_cancel, col_delete = st.columns([1, 1, 2], vertical_alignment="bottom")
    if col_save.button("Salva", type="primary", width="stretch", key=f"{key}_save"):
        body = {"description": description, "role_name": role_name, "prompt_id": prompt_id,
                "model": model or "", "max_steps": int(max_steps), "tool_names": tool_names}
        try:
            if current is None:
                agents_api.create_agent({"name": name, "project_name": scope, **body})
            else:
                agents_api.update_agent(current.name, body)
        except ApiError as exc:
            st.error(str(exc))
            return
        st.rerun()
    if col_cancel.button("Annulla", width="stretch", key=f"{key}_cancel"):
        st.rerun()
    if current is not None:
        with col_delete.popover("Elimina agente", width="stretch"):
            st.write(f"Eliminare definitivamente **{current.name}**? Le run passate restano.")
            if st.button("Sì, elimina", type="primary", key=f"{key}_delete"):
                try:
                    agents_api.delete_agent(current.name)
                except ApiError as exc:
                    st.error(str(exc))
                    return
                st.rerun()


# --------------------------------------------------------------- prompts tab

def _prompts_tab(scope: str | None) -> None:
    agents_api = api().agents
    roles = agents_api.roles(scope)
    if not roles:
        st.info("Crea prima un ruolo.")
        return

    role_name = st.selectbox(
        "Ruolo", [role.name for role in roles],
        format_func=lambda name: name if _is_active_role(roles, name) else f"{name} (disattivato)",
        key=f"prompt_role_{_key(scope)}",
    )
    versions = agents_api.prompts(role_name)
    latest = versions[0] if versions else None

    st.caption(
        "Le versioni sono immutabili: salvando crei una nuova versione, "
        "le configurazioni restano sulla versione che hanno scelto."
    )
    text = st.text_area("System prompt", value=latest.text if latest else "", height=200, key=f"prompt_text_{role_name}")
    if st.button("Salva come nuova versione", key=f"prompt_save_{role_name}"):
        try:
            result = agents_api.create_prompt_version(role_name, text)
        except ApiError as exc:
            st.error(str(exc))
            return
        if not result.created:
            st.info("Testo identico all'ultima versione: nessuna nuova versione creata.")
        else:
            st.success(f"Creata la versione v{result.prompt.version}.")
            st.rerun()

    for version in versions:
        status = "✅ attiva" if version.active else "⏸️ disattivata"
        with st.expander(f"v{version.version} · {version.created_at.astimezone():%Y-%m-%d %H:%M} · {status}"):
            st.text(version.text)
            if st.button("Disattiva" if version.active else "Riattiva", key=f"prompt_toggle_{version.id}"):
                try:
                    agents_api.set_prompt_active(version.id, not version.active)
                except ApiError as exc:
                    st.error(str(exc))
                    return
                st.rerun()


# ----------------------------------------------------------------- roles tab

def _roles_tab(scope: str | None) -> None:
    agents_api = api().agents
    roles = agents_api.roles(scope)
    k = _key(scope)
    if roles:
        rows = [
            {"ruolo": role.name, "descrizione": role.description, "stato": "✅ attivo" if role.active else "⏸️ disattivato"}
            for role in roles
        ]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

        col_role, col_toggle = st.columns([3, 1], vertical_alignment="bottom")
        role_name = col_role.selectbox("Ruolo", [role.name for role in roles], key=f"role_toggle_select_{k}")
        active = _is_active_role(roles, role_name)
        if col_toggle.button("Disattiva" if active else "Riattiva", key=f"role_toggle_{role_name}"):
            try:
                agents_api.set_role_active(role_name, not active)
            except ApiError as exc:
                st.error(str(exc))
                return
            st.rerun()

    with st.form(f"role_form_{k}", clear_on_submit=True):
        name = st.text_input("Nome del ruolo")
        description = st.text_input("Descrizione")
        if st.form_submit_button("Salva ruolo"):
            try:
                agents_api.create_role(name, scope, description)
            except ApiError as exc:
                st.error(str(exc))
                return
            st.rerun()


def _is_active_role(roles: list[Role], name: str) -> bool:
    return any(role.name == name and role.active for role in roles)
