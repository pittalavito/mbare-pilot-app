# `src/controller`

L'API HTTP del backend (FastAPI), un router per ambito. I controller sono sottili: leggono la richiesta, chiamano un [service](../service/README.md), convertono il risultato nella response.

Tutti i path stanno sotto `/api`. L'elenco completo degli endpoint, con parametri e modelli, è nella documentazione interattiva: `<API_URL>/api/docs` (Swagger), con l'API accesa.

```
src/controller/
  router.py                    aggrega i router + GET /health
  dependencies.py              i service del Container, da usare con Depends(...)
  project_controller.py        /projects
  folder_controller.py         /folders: la scelta delle cartelle, dentro PROJECT_ROOTS
  project_data_controller.py   /projects/{p}: note, attività, agent task, riferimenti, file, ricerca nel codice, impostazioni della zona
  saved_search_controller.py   /projects/{p}/code-search/saved, /regex: ricerche salvate e «✨ Regex»
  activity_draft_controller.py /projects/{p}/activities/draft: «📎 Parto da riferimenti»
  plan_controller.py           /projects/{p}/activities/{a}: piano, percorso, giro, pre e post, chiusura, archivio
  today_controller.py          /projects/{p}/today: «📌 Oggi», spunta e rimanda una voce
  wip_controller.py            /projects/{p}/wip: «Elabora WIP»
  copilot_controller.py        sessioni di Copilot: chat, ok, esecuzione, salva come nota, uso
  publish_controller.py        /projects/{p}/agent-tasks/{nota}/publish: anteprima e pubblicazione della bozza
  dev_controller.py            /projects/{p}: test dei repository, Operatore, comandi permessi e richieste, un comando a mano
  git_controller.py            /projects/{p}/git: repository, log, stato (sola lettura)
  atlassian_controller.py      /projects/{p}/atlassian: sito, Jira, Confluence, preferiti, copia come riferimento
  context_controller.py        /projects/{p}/context, /context-index: contesto e RAG, mappa dei repository
  masking_controller.py        /projects/{p}/masking
  chatbot_controller.py        chatbot, conversazioni, messaggi, cache delle automation
  agent_controller.py          /agents (?project= per quelli di un progetto)
  role_controller.py           /roles, /prompts
  catalog_controller.py        /tools, /models
  pipeline_controller.py       automation, run, YAML, tool degli step, worker
  definition_controller.py     /projects/{p}/definitions: anteprima e sincronizzazione dai file
  metrics_controller.py        /observability/metrics, /observability/evaluations
  admin_controller.py          /admin/config, /observability/runs (trace, cosa ha visto il modello), backup, /roadmap
  process_controller.py        /admin/worker, /admin/logs/{processo}
  tool_request_controller.py   /admin/tool-requests: richieste di tool e token di Claude Code
  mcp_server.py                /mcp: server MCP per Copilot (un'app montata, non un router)
  dev_mcp_server.py            /mcp-dev: server MCP per Claude Code
```

## Server MCP

- **`/mcp`, per Copilot** (streamable HTTP, senza stato, risposte JSON): `read_task`, `list_references`, `read_reference`, `search_context`, e in esecuzione `ask_user` (la domanda va in chat e aspetta la risposta) e `finish` (uno sviluppo passa a «da verificare»). Ogni chiamata porta il token della sessione e vede solo il suo task. Niente masking: Copilot legge già il codice in chiaro.
- **`/mcp-dev`, per Claude Code** sul clone di mbare-pilot-app: `list_tool_requests`, `read_tool_request`, `update_tool_request`, con il token generato in Admin → Richieste di tool.

Entrambi stanno fuori dallo schema OpenAPI. I tool sono sincroni e girano in un thread, così `ask_user` può aspettare senza fermare il server.

## Convenzioni

- **Service da `Depends`**: `service: ProjectService = Depends(project_service)`; i provider in `dependencies.py` danno i service del Container creato all'avvio.
- **Request e response** in [`models/controller/`](../models/README.md): i modelli di dominio non escono dai controller.
- **Errori**: un `AppError` di un service diventa lo status giusto in `core/app.py` (404, 400, 409, 502) con il messaggio in `detail`; un body malformato è il 422 di FastAPI.
- **Nomi negli URL**: nomi di progetti e agenti finiscono nei path, quindi niente `/` né `\`.
- **File**: l'upload è il body grezzo di un `PUT`, il download restituisce i byte.
- **Niente streaming**: un messaggio in chat aspetta la risposta intera.

## Aggiungere un endpoint

1. Request e response in `models/controller/<ambito>.py`.
2. La route in `controller/<ambito>_controller.py` (un ambito nuovo = un file nuovo con il suo `APIRouter`, incluso in `router.py`).
3. Se serve un service nuovo, il suo provider in `dependencies.py`.
4. Rigenera i tipi del frontend: `npm run gen:api` in `web/`.

## Test

`test/unit/api/`: `TestClient` sull'app vera, con un Container sugli store di test e modelli finti.
