"""Chat tab of a project: its chatbot (one per project, created and edited
here, with its own agent: system prompt, model, tools), its conversations on
the left and the open conversation on the right. A reply arrives whole (no
streaming yet).

Cache: under each user message «⚡ Metti in cache» links it to an automation
and a fixed input; similar messages then launch it without the agent (replies
starting with ⚡). A message starting with ``!`` skips the cache."""
import streamlit as st

from api_client.client import ApiError
from api_client.models import Chatbot, ChatRoute, Message, Pipeline
from views.model_picker import model_select
from views.services import api


def chat_section(project_name: str) -> None:
    key = f"chat_{project_name}"
    chatbots = api().chat.chatbots(project_name)
    if not chatbots:
        st.info("Nessun chatbot: crea quello del progetto e configura il suo agente (prompt, modello, tool).")
        if st.button("➕ Crea il chatbot", type="primary", key=f"{key}_first"):
            _chatbot_dialog(project_name, None)
        return

    chatbot = chatbots[0]  # one chatbot per project (the first by name, if more were created before)
    col_side, col_chat = st.columns([1, 3], gap="medium")
    with col_side:
        col_name, col_edit = st.columns([3, 2], vertical_alignment="center")
        col_name.markdown(f"**{chatbot.name}**")
        if col_edit.button("✏️ Modifica", width="stretch", key=f"{key}_edit"):
            _chatbot_dialog(project_name, chatbot)
        tools = ", ".join(f"`{tool}`" for tool in chatbot.tool_names) or "nessun tool"
        st.caption(f"`{chatbot.model}` · prompt v{chatbot.prompt_version} · {tools}")
        if chatbot.description:
            st.caption(chatbot.description)
        st.divider()
        conversation_id = _conversations(chatbot, f"{key}_{chatbot.id}")
    with col_chat:
        _conversation(chatbot, conversation_id, f"{key}_{chatbot.id}")


# ------------------------------------------------------------ conversations

def _conversations(chatbot: Chatbot, key: str) -> int | None:
    """The conversation list; returns the open one (None = a new one, created
    on the first message)."""
    open_key = f"{key}_conversation"
    if st.button("💬 Nuova conversazione", width="stretch", key=f"{key}_new_conversation"):
        st.session_state[open_key] = None
    conversations = api().chat.conversations(chatbot.id)
    if st.session_state.get(open_key) not in {conversation.id for conversation in conversations}:
        st.session_state[open_key] = None
    with st.container(height=420, border=False):
        for conversation in conversations:
            is_open = conversation.id == st.session_state[open_key]
            label = conversation.title or "Nuova conversazione"
            if st.button(label, key=f"{key}_open_{conversation.id}", width="stretch",
                         type="primary" if is_open else "secondary"):
                st.session_state[open_key] = conversation.id
                st.rerun()
        if not conversations:
            st.caption("Nessuna conversazione.")
    return st.session_state[open_key]


def _conversation(chatbot: Chatbot, conversation_id: int | None, key: str) -> None:
    chat = api().chat
    messages = chat.messages(conversation_id) if conversation_id is not None else []
    routes = {route.message_id: route for route in chat.routes(chatbot.id) if route.message_id is not None}
    automations = [p for p in api().automation.pipelines(chatbot.project_name) if p.active and p.steps]
    if error := st.session_state.pop(f"{key}_route_error", None):
        st.error(error)
    with st.container(height=520, border=True):
        if not messages:
            st.caption(f"Scrivi per iniziare una conversazione con **{chatbot.name}**.")
        for index, message in enumerate(messages):
            reply = messages[index + 1] if index + 1 < len(messages) else None
            _message(message, routes.get(message.id), automations, reply, key)

    text = st.chat_input(f"Scrivi a {chatbot.name}… (inizia con ! per saltare la cache)", key=f"{key}_input")
    if text:
        try:
            if conversation_id is None:
                conversation_id = chat.new_conversation(chatbot.id).id
                st.session_state[f"{key}_conversation"] = conversation_id
            with st.spinner(f"{chatbot.name} sta rispondendo…"):
                chat.send(conversation_id, text)
        except ApiError as exc:
            st.error(str(exc))
            return
        st.rerun()

    if conversation_id is not None:
        with st.popover("🗑️ Elimina conversazione"):
            st.write("Eliminare questa conversazione e i suoi messaggi?")
            if st.button("Sì, elimina", type="primary", key=f"{key}_delete_{conversation_id}"):
                chat.delete_conversation(conversation_id)
                st.session_state[f"{key}_conversation"] = None
                st.rerun()


def _message(message: Message, route: ChatRoute | None, automations: list[Pipeline], reply: Message | None,
             key: str) -> None:
    if message.role == "user":
        with st.chat_message("user"):
            st.markdown(message.content)
            _cache_controls(message, route, automations, reply, key)
    elif message.role == "assistant":
        avatar = "⚡" if message.content.startswith(_CACHE_MARK) else None
        st.chat_message("assistant", avatar=avatar).markdown(message.content)
    else:
        st.chat_message("assistant", avatar="⚠️").error(message.content)


# -------------------------------------------------------------------- cache
# Buttons act in callbacks (as in the automation editor): the chat input and
# the reruns it triggers can swallow a click read as a return value.

_CACHE_MARK = "⚡"
"""Starts the replies given from the cache (CACHE_MARK of the backend)."""


def _cache_controls(message: Message, route: ChatRoute | None, automations: list[Pipeline], reply: Message | None,
                    key: str) -> None:
    """Under a user message: what it launches when in cache, else «Metti in cache»."""
    by_id = {automation.id: automation for automation in automations}
    if route is not None:
        name = by_id[route.pipeline_id].name if route.pipeline_id in by_id else f"automation {route.pipeline_id}"
        details = f" · input «{route.pipeline_input}»" if route.pipeline_input else ""
        col_info, col_remove = st.columns([6, 1], vertical_alignment="center")
        col_info.caption(f"⚡ In cache → **{name}**{details} · usata {route.hits} volte")
        col_remove.button("🗑", key=f"{key}_route_remove_{route.id}", help="Togli dalla cache",
                          on_click=_remove_route, args=(route.id, key))
        return
    if not automations:
        return
    with st.popover("⚡ Metti in cache"):
        st.caption("I messaggi simili lanceranno questa automation direttamente, senza l'agente.")
        ids = list(by_id)
        # Proposed: the automation the reply names (e.g. the one the agent launched).
        mentioned = next((i for i, a in by_id.items() if reply is not None and a.name in reply.content), ids[0])
        widget = f"{key}_route_{message.id}"
        st.selectbox("Automation", ids, index=ids.index(mentioned), format_func=lambda i: by_id[i].name,
                     key=f"{widget}_pipeline")
        st.text_input("Input fisso", key=f"{widget}_input", help="Lo stesso per ogni messaggio simile (vuoto = nessuno).")
        st.button("Salva", type="primary", key=f"{widget}_save", on_click=_add_route, args=(message.id, widget, key))


def _add_route(message_id: int, widget: str, key: str) -> None:
    try:
        api().chat.add_route(message_id, st.session_state[f"{widget}_pipeline"],
                             st.session_state.get(f"{widget}_input", ""))
    except ApiError as exc:
        st.session_state[f"{key}_route_error"] = str(exc)


def _remove_route(route_id: int, key: str) -> None:
    try:
        api().chat.delete_route(route_id)
    except ApiError as exc:
        st.session_state[f"{key}_route_error"] = str(exc)


# ------------------------------------------------------------------ dialog

@st.dialog("Chatbot", width="large")
def _chatbot_dialog(project_name: str, current: Chatbot | None) -> None:
    """Create (``current`` None) or edit a chatbot and its agent; editing also deletes it."""
    chat = api().chat
    key = f"chatbot_form_{project_name}_{current.id if current else 'new'}"

    name = st.text_input("Nome", value=current.name if current else "", key=f"{key}_name")
    description = st.text_input("Descrizione", value=current.description if current else "", key=f"{key}_description")

    st.markdown("**Agente del chatbot**")
    system_prompt = st.text_area(
        "System prompt", value=current.system_prompt if current else "", height=200,
        placeholder="Chi è il chatbot, cosa sa del progetto, come risponde, quando usare i tool…",
        help="Cambiarlo crea la versione successiva del prompt, registrata in ogni run.",
        key=f"{key}_prompt",
    )
    col_model, col_steps = st.columns([3, 1])
    model = model_select(col_model, current.model if current else None, key=f"{key}_model")
    max_steps = col_steps.number_input(
        "Max steps", min_value=1, max_value=50, value=current.max_steps if current else 4,
        help="Quante volte l'agente può chiamare i tool per una risposta.", key=f"{key}_steps",
    )
    tools = {tool.name: tool for tool in api().agents.tools() if tool.available}
    tool_names = st.multiselect(
        "Tool", list(tools), default=[name for name in (current.tool_names if current else []) if name in tools],
        format_func=lambda tool_name: f"{tool_name} — {tools[tool_name].description}" if tools[tool_name].description else tool_name,
        key=f"{key}_tools",
    )
    missing = [name for name in (current.tool_names if current else []) if name not in tools]
    if missing:
        st.warning(f"Tool non più disponibili, verranno rimossi al salvataggio: {', '.join(missing)}")

    st.divider()
    col_save, col_cancel, col_delete = st.columns([1, 1, 2], vertical_alignment="bottom")
    if col_save.button("Salva", type="primary", width="stretch", key=f"{key}_save"):
        body = dict(
            name=name, system_prompt=system_prompt, model=model, description=description,
            max_steps=int(max_steps), tool_names=tool_names,
        )
        try:
            if current is None:
                chat.create_chatbot(project_name, body)
            else:
                chat.update_chatbot(current.id, body)
        except ApiError as exc:
            st.error(str(exc))
            return
        st.rerun()
    if col_cancel.button("Annulla", width="stretch", key=f"{key}_cancel"):
        st.rerun()
    if current is not None:
        with col_delete.popover("Elimina chatbot", width="stretch"):
            st.write(f"Eliminare **{current.name}** e tutte le sue conversazioni? Le run degli agenti restano.")
            if st.button("Sì, elimina", type="primary", key=f"{key}_delete"):
                chat.delete_chatbot(current.id)
                st.rerun()
