# `src/controller`

L'API HTTP del backend (FastAPI): un router per ambito. I controller sono sottili: leggono la richiesta, chiamano un service, convertono il risultato nella response. Le regole stanno nei [service](../service/README.md).

```
src/controller/
  router.py                   aggrega tutti i router + GET /health
  dependencies.py             i service del Container, da usare con Depends(...)
  project_controller.py       /projects
  folder_controller.py        /folders
  agent_controller.py         /agents
  role_controller.py          /roles, /prompts
  catalog_controller.py       /tools, /models
  chatbot_controller.py       chatbot, conversazioni, messaggi
  project_data_controller.py  /projects/{progetto}/notes, /files
  git_controller.py           /projects/{progetto}/git
  pipeline_controller.py      automation, run, /functions, /workers
  atlassian_controller.py     /projects/{progetto}/atlassian
  masking_controller.py       /projects/{progetto}/masking
  definition_controller.py    /projects/{progetto}/definitions (anteprima), .../sync
  process_controller.py       /admin/worker, /admin/logs/{processo}
  admin_controller.py         /admin/config, /observability
```

Tutti i path qui sotto stanno sotto `/api` (`core/server.py` monta l'API lì e serve il frontend altrove). Documentazione interattiva con tutti gli endpoint: `<API_URL>/api/docs` (Swagger), con l'API accesa.

## Endpoint

| Ambito | Endpoint |
|---|---|
| Salute | `GET /health` |
| Progetti | `GET /projects`, `GET /projects/options`, `GET /projects/{nome}`, `POST /projects/open-folder`, `POST /projects/from-scratch`, `PATCH /projects/{nome}`, `DELETE /projects/{nome}` |
| Cartelle | `GET /folders/roots`, `GET /folders?path=&show_hidden=` |
| Agenti | `GET /agents?project=&include_global=`, `GET/PUT/DELETE /agents/{nome}`, `POST /agents` |
| Ruoli e prompt | `GET/POST /roles`, `PATCH /roles/{nome}`, `GET/POST /roles/{nome}/prompts`, `PATCH /prompts/{id}` |
| Cataloghi | `GET /tools`, `GET /models/choices?current=`, `GET/PUT /models` |
| Chat | `GET/POST /projects/{p}/chatbots`, `PUT/DELETE /chatbots/{id}`, `GET/POST /chatbots/{id}/conversations`, `DELETE /conversations/{id}`, `GET/POST /conversations/{id}/messages`; cache: `GET /chatbots/{id}/routes`, `POST /messages/{id}/route`, `DELETE /chat-routes/{id}` |
| Dati | `GET /projects/{p}/notes` (con `note_type`), `GET/PUT/DELETE /projects/{p}/notes/{nota}`, `GET/POST /projects/{p}/agent-tasks`, `PUT /projects/{p}/agent-tasks/{nota}`, `GET/POST /projects/{p}/todo-lists`, `PUT /projects/{p}/todo-lists/{nota}`, `GET/POST /projects/{p}/references`, `PUT/DELETE /projects/{p}/references/{nota}` (riferimenti di codice e contesto, con `linked_from`; cancellarne uno lo scollega ovunque), `GET/PUT /projects/{p}/data-settings` (i tipi di nota che mostra la scheda Dati), `GET /projects/{p}/files`, `GET/PUT/DELETE /projects/{p}/files/{file}` |
| Git | `GET /projects/{p}/git/repositories`, `GET .../git/log?path=&limit=&author=&message=&commit=`, `GET .../git/status?path=` |
| Automation | `GET/POST /projects/{p}/pipelines`, `PUT/DELETE /pipelines/{id}`, `GET/POST /pipelines/{id}/runs`, `DELETE /pipeline-runs/{id}`, `GET /functions`, `GET /workers`, `GET /workers/health` |
| Atlassian | `GET/PUT/DELETE /projects/{p}/atlassian`, `POST .../atlassian/check`, `GET .../atlassian/jira/issues/{chiave}`, `GET .../atlassian/confluence/pages`, `GET .../atlassian/confluence/pages/{id}`, `GET .../atlassian/confluence/search?q=`, `GET/POST .../atlassian/favorites`, `DELETE .../atlassian/favorites/{id}` |
| Mascheramento | `GET/POST /projects/{p}/masking`, `DELETE /projects/{p}/masking/{alias}` |
| Processi | `GET /admin/worker`, `POST /admin/worker/start`, `POST /admin/worker/stop` (409 se ne gira uno avviato altrove), `GET /admin/logs/{api\|worker}?lines=` |
| Definizioni da file | `GET /projects/{p}/definitions` (anteprima), `POST /projects/{p}/definitions/sync` (tutto, o `only` gli elementi scelti; vedi [definitions](../../definitions.md)) |
| Copilot | `GET /copilot/status[?project=]` (CLI, coding agent, prompt e modelli da scegliere con prezzo e costo medio per turno), `GET /copilot-sessions/{id}/turns` (uso per turno e totale), `GET /observability/copilot/turns[?limit=&project=]`, `GET /observability/copilot/models[?days=&project=]`, `GET/POST/DELETE /projects/{p}/copilot-sessions` (DELETE `?task_note=`: le sessioni di un task), `GET/DELETE /copilot-sessions/{id}`, `GET/POST /copilot-sessions/{id}/messages`, `POST /copilot-sessions/{id}/approve`, `POST /copilot-sessions/{id}/cancel` |
| Admin | `GET /admin/config`, `GET /observability/runs`, `GET /observability/runs/{run_id}/trace`, `GET /observability/tool-calls`, `GET/POST /admin/backups`, `GET /admin/backups/{nome}` |

## Convenzioni

- **Service da `Depends`**: `service: ProjectService = Depends(project_service)`. I provider in `dependencies.py` restituiscono i service del Container creato all'avvio (`app.state.container`).
- **Request e response** stanno in [`models/controller/`](../models/README.md): i modelli di dominio non escono mai dai controller.
- **Errori**: i controller non li gestiscono. Un `AppError` sollevato da un service diventa lo status HTTP giusto in `core/app.py` (404, 400, 409, 502) con il messaggio in `detail`; i dati rifiutati da un modello di dominio diventano 400; un body malformato è il 422 di FastAPI.
- **Nomi negli URL**: i nomi dei progetti e degli agenti finiscono nei path, quindi non possono contenere `/` o `\`.
- **File**: l'upload è il body grezzo di un `PUT` (niente multipart), il download restituisce i byte.
- **Automation**: `steps` + `edges` (`source`, `target`, `condition`, `value`; `source` può essere `input`); `edges` vuoto = la catena degli step.
- **Streaming**: non ancora. `POST /conversations/{id}/messages` aspetta la risposta intera dell'agente.

## Aggiungere un endpoint

1. Request e response in `models/controller/<ambito>.py`.
2. La route in `controller/<ambito>_controller.py`; un ambito nuovo è un file nuovo con il suo `APIRouter`.
3. Se serve un service nuovo, il suo provider in `dependencies.py`.
4. L'`include_router` in `router.py`.
5. Rigenera il client del frontend: `npm run gen:api` in `web/` (i tipi vengono dall'OpenAPI).

## Test

In `test/unit/api/`: `test_projects_api.py`, `test_agents_api.py`, `test_project_areas_api.py` (chat, dati, git, automation, Atlassian, admin). Usano `TestClient` sull'app vera con un Container sugli store in memoria e agenti finti.
