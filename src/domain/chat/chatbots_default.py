"""The chatbots every project has: created when the project is created and, at
startup, in the projects that miss them (by name). Only created, never
updated: a chatbot with the same name in global-chat-bots.yml / chat-bots.yml
replaces prompt and model when synced (Settings → Definizioni da file). The
UI does not create, edit nor delete chatbots."""
from models.domain.chatbot import ChatbotKind
from models.domain.definitions import ChatbotFile

_MODEL = "openrouter/google/gemini-3.1-flash-lite-preview"

DEFAULT_CHATBOTS: list[ChatbotFile] = [
    ChatbotFile(
        name="Chat bot",
        kind=ChatbotKind.AUTOMATION,
        description="Lancia le automation del progetto e ne controlla lo stato",
        model=_MODEL,
        max_steps=4,
        system_prompt=(
            "Sei il mio assistente sulle automation del progetto. Rispondi in italiano, breve.\n"
            "Per ogni richiesta guarda quali automation ci sono con list_automations, lancia quella adatta con\n"
            "run_automation, dimmi quale e con che id, e non aspettare.\n"
            "Se chiedo come è andata, controlla con automation_status.\n"
            "Se nessuna automation è adatta, dimmelo; se non sai, non inventare."
        ),
    ),
    ChatbotFile(
        name="Segretario",
        kind=ChatbotKind.SECRETARY,
        description="Todo list e stato degli agent task",
        model=_MODEL,
        max_steps=6,
        system_prompt=(
            "Sei il mio segretario sul progetto. Rispondi in italiano, breve.\n"
            "Mi aiuti con le todo list: le leggi, ne crei di nuove, aggiungi voci e le spunti; non le cancelli né le rinomini.\n"
            "Prima di modificare una lista leggila con read_todo_list e usa i numeri delle voci.\n"
            "Per le scadenze usa la data di oggi che ti danno i tool (es. «entro venerdì» → la data precisa).\n"
            "Sugli agent task mi dici solo lo stato (e quello dell'ultima sessione Copilot) con list_agent_tasks.\n"
            "Se non sai, non inventare."
        ),
    ),
]
"""The default chatbots, as a definition file would write them."""
