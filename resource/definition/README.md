# Definizioni di default

Le definizioni dell'app, versionate con il codice: l'app le legge da qui. All'avvio allinea da sola agenti, chatbot e automation a questi file (e a quelli della cartella dati).

```
agents/          agents.yml (Libreria), chatbots.yml (di ogni progetto)
automations/     automations.yml (di ogni progetto)
coding-agents/   quello che l'app dice ai coding agent, uno per cartella
  copilot/       coding-agent.yml + prompts/<nome>.md
  claude/        tool-requests.md
templates/       la struttura delle bozze: confluence.md, jira.md
context/         il contesto generale degli agenti (RAG)
board/           roadmap.yml (la bacheca), code-searches.yml (ricerche salvate)
```

| File | Cosa |
|---|---|
| `agents/agents.yml` | gli agenti della Libreria: l'esempio `hello` e quelli che l'app chiama da sola con risposta strutturata (`wip`, `pianificatore`, `bozza-attivita`, `imparato`, `regex`) |
| `agents/chatbots.yml` | i chatbot di ogni progetto (salvo stesso nome nel progetto) |
| `automations/automations.yml` | «Prova git»: stato git di tutti i repository salvato in una nota |
| `coding-agents/copilot/coding-agent.yml` | prompt, divieti e modelli (con i prezzi) di Copilot: **senza questo Copilot non parte** |
| `coding-agents/copilot/prompts/*.md` | i prompt di preparazione da scegliere quando deleghi (`analisi.md` per i task di analisi, `bugfix.md`, `confluence.md`, `jira.md`) |
| `coding-agents/claude/tool-requests.md` | cosa riceve Claude Code quando si collega al server MCP dev (richieste di tool); vale dal riavvio dell'API |
| `templates/*.md` | la struttura delle bozze Confluence e Jira: un prompt la riceve con `{template}` |
| `context/*.md` | il contesto generale per gli agenti: come funziona l'app, un file per tema; si cerca con `search_context` in ogni progetto |
| `board/roadmap.yml` | la bacheca «🚀 Mbare Pilot» (dalla UI si scrive la copia nella cartella dati) |
| `board/code-searches.yml` | le ricerche salvate nel codice di ogni progetto: TODO, FIXME, Commenti Mbare Pilot |

**Cambiarle senza toccare l'app**: in `<MBARE_PILOT_HOME>/definition/` metti solo quello che cambi, con la **stessa struttura**.
- In `agents/agents.yml`, `agents/chatbots.yml`, `automations/automations.yml` un elemento con lo **stesso nome** vince su quello di qui; gli altri restano questi (il tuo `agents/chatbots.yml` può contenere solo il Refiner cambiato).
- Negli altri file vince il file con lo **stesso percorso**.
- Dalla UI di un chatbot, «Salva prompt» o il cambio di modello scrivono il chatbot lì (diventa «tuo»); «↩ Torna al default» lo toglie.
- I file di un progetto stanno solo lì, in `project/<slug>/` con la stessa struttura: `agents/agents.yml`, `agents/chatbots.yml`, `automations/automations.yml`, `coding-agents/copilot/coding-agent.yml`, `coding-agents/copilot/prompts/`, `templates/`.
- I nomi della struttura vecchia (`global-agent.yml`, `global-chat-bots.yml`, `global-automation.yml`, `global-coding-agent.yml`, `coding-agent/`, `code-searches.yml`, `roadmap.yml`; nei progetti `agent.yml`, `chat-bots.yml`, `automation.yml`, `coding-agent.yml`, `coding-agent/`) non si leggono più: l'avvio li segnala nel log, vanno spostati a mano.

Formato e regole: [definitions.md](../../docs/doc/definitions.md). Un test (`test/unit/test_definition_examples.py`) verifica che questi file restino validi.
