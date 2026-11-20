# `src/tool`

I tool che un agente può chiamare durante una run, e che gli step `tool` delle automation usano. C'è un solo registro (`registry.py`): lo stesso tool vale in chat e nelle automation.

## Come funziona

```
avvio:  TOOL_REGISTRY ──sync──► tabella tool (catalogo: nome + descrizione)
UI:     un agente, un chatbot o uno step sceglie i tool dal catalogo, per nome
run:    AgentService ──build_tools(nomi, ToolContext)──► tool datapizza ──► agente
```

- **`ToolSpec`** (`spec.py`): nome, descrizione, come costruirlo; `static(f)` per un tool che non usa niente della run. `writes=True` segna un tool che cambia qualcosa; `chatbot_only=True` uno che funziona solo nelle run di un chatbot.
- **Catalogo**: all'avvio il registro si copia nella tabella `tool`. Un tool tolto dal codice resta con `available = False`: non si può più scegliere, e gli agenti che lo usano non partono finché non lo tolgono.
- **`ToolContext`** (`context.py`): il progetto della run, i servizi che un tool può usare (git, dati del progetto, automation, Copilot, RAG, comandi…), l'origine della run e la nota aperta accanto alla chat. I `require_*()` danno il servizio o un `ValidationError`.
- **Il progetto lo decide la run, non il modello**: un tool cerca sempre dentro il progetto della run, un agente non legge un altro progetto.
- **Masking**: non sta nei tool. `AgentMask` (`domain/agent/masking.py`) smaschera gli argomenti e maschera l'output. Un tool restituisce il suo modello di output (`models/domain/tool.py`) e dichiara i valori sensibili con i tipi di `models/domain/masking.py` (es. `MaskRepositoryName`).
- **Errori**: i tool git restituiscono `{"error": "..."}` con i repository disponibili invece di fermare la run (`list/git/errors.py`); i percorsi locali diventano `<progetto>` e `~`.
- **Argomenti** (`list/git/params.py`): tutti obbligatori, `''` per «non usato», così lo schema vale anche in strict mode.

## I tool (`list/`)

| Gruppo | Tool | Chi li usa |
|---|---|---|
| git | `git_status`, `git_log`, `git_diff`, `git_branches`, `git_stash_list`, `git_fetch` (lettura); `git_checkout`, `git_create_branch`, `git_pull_fast_forward`, `git_pull_by_branch`, `git_pull_all_by_branch`, `git_stash`, `git_stash_apply`, `git_commit`, `git_push` | Dev, automation (commit e push non sono tra i tool di Dev) |
| sviluppo | `git_check_clean`, `git_checkout_branches` (pre), `run_tests` (post: tutti i test o solo i toccati), `run_command` (comandi permessi del progetto) | Dev, automation |
| Maven | `maven_parent_alignment`, `coverage_new_code` | Dev, automation |
| codice | `search_code`, `save_code_search` | chatbot (Refiner, Dev); salvare solo Dev, con l'ok |
| contesto | `search_context` | tutti i chatbot di default e il Pianificatore |
| note | `save_note` | agenti e automation |
| Segretario | attività (`list_activities`, `read_activity`, `create_activity`, `update_activity`), agent task (`list_agent_tasks`, `list_references`, `create_agent_task`), `today` | chatbot |
| Refiner | `read_agent_task`, `update_agent_task`, `finish_refinement`: solo sul task aperto accanto alla chat | Refiner |
| Copilot | `delegate_task`, `copilot_status` | chatbot |
| automation | `list_automations`, `run_automation`, `automation_status` | chatbot |
| Architetto | `list_tools`, `list_agents`, `read_automation`, `validate_automation`, `request_tool` (dopo l'ok dell'utente) | Architetto |
| esempio | `hello_world` | — |

## Aggiungere un tool

1. Il modello di output in `models/domain/tool.py`, con i campi sensibili tipati.
2. Un file in `list/<gruppo>/`: una funzione `build(context) -> Tool` e la sua `ToolSpec` (o `@tool` + `static(...)` se non usa la run).
3. La spec in `registry.py`. Se serve un servizio nuovo, va in `ToolContext` e lo passa `AgentService`.
4. I test in `test/unit/tool/`. Si prova anche da Admin → Tool.

Un tool che manca a un'automation lo chiede l'Architetto con `request_tool`; Claude Code lo scrive da qui, con i test, e apre la PR.
