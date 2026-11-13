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
  wip_controller.py           /projects/{progetto}/wip
  context_controller.py       /projects/{progetto}/context, /context-index (RAG)
  metrics_controller.py       /observability/metrics, /observability/evaluations
  today_controller.py         /projects/{progetto}/today, Spunta e Rimanda di una voce
  publish_controller.py       /projects/{progetto}/agent-tasks/{nota}/publish: anteprima e pubblicazione della bozza
  dev_controller.py           /projects/{progetto}/dev-settings: test e automation delle verifiche dello sviluppo
  mcp_server.py               /mcp: il server MCP per Copilot (non è un router: un'app MCP montata da core/app.py)
  definition_controller.py    /projects/{progetto}/definitions (anteprima), .../sync
  process_controller.py       /admin/worker, /admin/logs/{processo}
  admin_controller.py         /admin/config, /observability
```

Tutti i path qui sotto stanno sotto `/api` (`core/server.py` monta l'API lì e serve il frontend altrove). Documentazione interattiva con tutti gli endpoint: `<API_URL>/api/docs` (Swagger), con l'API accesa.

## Server MCP per Copilot

`mcp_server.py` costruisce il server MCP dell'app (SDK `mcp`, `MCPServer`) e `core/app.py` lo monta su **`/mcp`** (quindi `<API_URL>/api/mcp/`): trasporto *streamable HTTP*, senza stato tra le chiamate, risposte JSON. Lo usa **GitHub Copilot** mentre lavora su un agent task: l'app glielo passa a ogni turno con il token della sessione (vedi [service](../service/README.md#copilot)).

| Tool | Cosa fa |
|---|---|
| `read_task()` | il task della sessione: titolo, tipo, obiettivo, contesto, criteri, vincoli, checklist del tipo |
| `list_references()` | quello che il task collega (riferimenti, note, file) con nome, tipo, titolo, se esiste ancora |
| `read_reference(name)` | il contenuto di uno di loro, come testo |
| `ask_user(question)` | in esecuzione: la domanda va nella chat e il tool aspetta la risposta (fino al timeout) |
| `search_context(question)` | la ricerca nel contesto del progetto della sessione ([RAG](../service/README.md#contesto-rag)) |
| `finish(summary)` | in esecuzione: «ho finito», il riassunto in chat; uno sviluppo passa a «da verificare» |

- **Token**: ogni chiamata porta `Authorization: Bearer <token della sessione>`; i tool vedono solo il task di quella sessione. Un token sconosciuto (o di una sessione cancellata) è un errore del tool con il suo messaggio. Il controllo dell'Host (DNS rebinding) è spento: ogni tool vuole comunque il token.
- **Niente mascheramento**: Copilot legge già il codice in chiaro.
- **Tool sincroni in un thread**: `ask_user` può aspettare minuti senza fermare il server, e un turno di preparazione (che gira dentro una richiesta dell'API) può richiamare l'API stessa (provato da `test/unit/service/test_copilot_mcp.py`, con uvicorn vero e il Copilot finto).
- **Fuori dallo schema OpenAPI**: è un'app montata, non un router.

## Endpoint

| Ambito | Endpoint |
|---|---|
| Salute | `GET /health` |
| Progetti | `GET /projects`, `GET /projects/options`, `GET /projects/{nome}`, `POST /projects/open-folder`, `POST /projects/from-scratch`, `PATCH /projects/{nome}`, `DELETE /projects/{nome}` |
| Cartelle | `GET /folders/roots`, `GET /folders?path=&show_hidden=` |
| Agenti | `GET /agents?project=&include_global=`, `GET/PUT/DELETE /agents/{nome}`, `POST /agents` |
| Ruoli e prompt | `GET/POST /roles`, `PATCH /roles/{nome}`, `GET/POST /roles/{nome}/prompts`, `PATCH /prompts/{id}` |
| Cataloghi | `GET /tools`, `GET /models/choices?current=`, `GET/PUT /models` |
| Chat | `GET/POST /projects/{p}/chatbots`, `PUT/DELETE /chatbots/{id}`, `GET/POST /chatbots/{id}/conversations`, `DELETE /conversations/{id}`, `GET/POST /conversations/{id}/messages`; cache delle automation (solo chatbot `automation`): `GET /chatbots/{id}/automation-cache`, `POST /messages/{id}/automation-cache`, `DELETE /automation-cache/{id}` |
| Dati | `GET /projects/{p}/notes` (con `note_type`), `GET/PUT/DELETE /projects/{p}/notes/{nota}`, `GET/POST /projects/{p}/agent-tasks`, `PUT /projects/{p}/agent-tasks/{nota}` (con `items_changed`: le voci spuntate o despuntate perché il task è arrivato a «fatto» o l'ha lasciato), `GET/POST /projects/{p}/activities`, `POST /projects/{p}/activities/{nota}/items/{n}/agent-task` (`{text, type}`: «🤖» sulla voce n, crea il task collegato; 201, 409 se la voce è cambiata o ha già un task), `PUT /projects/{p}/activities/{nota}` (le attività, con gli agent task nati da loro; cancellare un agent task lo scollega da tutte), `GET/POST /projects/{p}/references`, `PUT/DELETE /projects/{p}/references/{nota}` (riferimenti di codice e contesto, con `linked_from`; cancellarne uno lo scollega ovunque), `GET/PUT /projects/{p}/data-settings` (i tipi di nota che mostra la zona Progetto, `files_visible` e `due_soon_days`, i giorni di «In scadenza»: omesso nel PUT resta com'è), `GET /projects/{p}/files`, `GET/PUT/DELETE /projects/{p}/files/{file}` |
| Git | `GET /projects/{p}/git/repositories`, `GET .../git/log?path=&limit=&author=&message=&commit=`, `GET .../git/status?path=`, `GET .../git/branches?path=` (branch corrente, locali e remoti: per sceglierne uno nella delega) |
| Automation | `GET/POST /projects/{p}/pipelines`, `PUT/DELETE /pipelines/{id}`, `POST /projects/{p}/pipelines/yaml/check` (`{yaml}`: valida senza salvare, con step, collegamenti, `replaces`, `system`; 400 con il motivo), `POST /projects/{p}/pipelines/yaml` (salva: crea o aggiorna quella con lo stesso nome), `GET /pipelines/{id}/yaml` (Esporta YAML), `GET /messages/{id}/learn-draft` (piano 11: le azioni riuscite di una risposta dell'Operatore e i campi proposti; 404 a traccia scaduta), `POST /projects/{p}/pipelines/learned` (`{name, purpose, steps, fields}`: la salva come automation di step tool), `GET/POST /pipelines/{id}/runs`, `DELETE /pipeline-runs/{id}`, `GET /functions`, `GET /workers`, `GET /workers/health` |
| Atlassian | `GET/PUT/DELETE /projects/{p}/atlassian`, `POST .../atlassian/check`, `GET .../atlassian/jira/issues/{chiave}`, `GET .../atlassian/jira/search?q=[&jira_project=]` (una chiave, anche dentro un link, apre quella issue; altro testo cerca in titolo e descrizione, nel progetto Jira indicato o ovunque; al massimo 20), `GET .../atlassian/jira/issue-types[?project_key=]` (i tipi creabili), `GET .../atlassian/confluence/pages[?space=]`, `GET .../atlassian/confluence/pages/{id}`, `GET .../atlassian/confluence/search?q=`, `POST .../atlassian/jira/issues/{chiave}/reference` e `POST .../atlassian/confluence/pages/{id}/reference` (copia in un riferimento di contesto, `{"link_to": [...]}`: 201 creato, 200 aggiornato, 409 nome preso da un altro), `GET/POST .../atlassian/favorites`, `DELETE .../atlassian/favorites/{id}` |
| Mascheramento | `GET/POST /projects/{p}/masking`, `DELETE /projects/{p}/masking/{alias}` |
| Pubblica | `GET /projects/{p}/agent-tasks/{nota}/publish` (anteprima: crea o aggiorna, titolo, corpo, alias smascherati, testo attuale per il confronto), `POST .../publish` (`{space_key, parent_id, project_key, issue_type}` per una pagina o issue nuova; il task va a «fatto», la pagina o issue diventa un riferimento collegato) |
| Verifiche dello sviluppo | `GET/PUT /projects/{p}/dev-settings` (test di ogni repository: strumento, comando rilevato e quello scritto; `test_scope` di default `all`/`touched`; se il progetto ha «Prepara sviluppo» e «Verifica sviluppo»; il PUT riceve `{test_scope, commands, allowed_commands, operator_chatbot_id}`; anche i comandi permessi dell'Operatore, quelli rilevati da proporre e l'Operatore della preparazione), `GET /projects/{p}/command-requests` (i comandi che l'Operatore ha chiesto), `POST /projects/{p}/command-requests/answer` (`{command, allow, always}`: «Sempre», «Solo stavolta», «No»; 404 senza richiesta) |
| Oggi | `GET /projects/{p}/today` («📌 Oggi»: `waiting`, `overdue`, `due_soon`, `to_close`, `due_soon_days`, `date`), `POST /projects/{p}/activities/{nota}/items/{n}/check` (`{text}`: spunta la voce n, 204; 409 se la voce è cambiata o è già fatta), `POST /projects/{p}/activities/{nota}/items/{n}/due` (`{text, due}`: nuova scadenza, 204) |
| Metriche | `GET /observability/metrics[?days=&project=]` (costo e latenza per chi, Copilot, accettazione di Elabora WIP), `GET /observability/evaluations` (valutazioni lanciate e report), `POST /observability/evaluations` (`{kind: wip|rag, models, embedders}`: in coda per il worker), `GET /observability/evaluations/reports/{nome}[?format=md|json]` |
| Contesto (RAG) | `GET /projects/{p}/context`, `GET/PUT/DELETE /projects/{p}/context/{nome}` (salvare indicizza: `index_error` dice se non ci è riuscito; cancellare toglie dall'indice), `GET /projects/{p}/context-index` (documenti, pezzi, embedder), `POST /projects/{p}/context-index/reindex`, `POST /projects/{p}/context-index/search` (quello che `search_context` dà a Refiner e Copilot) |
| Elabora WIP | `GET /projects/{p}/wip` (la nota e le parole del testo nuovo), `GET /projects/{p}/wip/runs` (le elaborazioni con l'esito), `POST /projects/{p}/wip/preview` (il testo che riceve il modello, mascherato, con gli alias), `POST /projects/{p}/wip/process` (una chiamata: le proposte in chiaro; 502 se il modello non risponde), `POST /projects/{p}/wip/apply` (le proposte scelte e il segno nella nota; 409 se la WIP è cambiata o le proposte sono già applicate o annullate), `POST /projects/{p}/wip/dismiss` (proposte chiuse senza applicarne nessuna: tutte scartate, niente segno) |
| Processi | `GET /admin/worker`, `POST /admin/worker/start`, `POST /admin/worker/stop` (409 se ne gira uno avviato altrove), `GET /admin/logs/{api\|worker}?lines=` |
| Definizioni da file | `GET /projects/{p}/definitions` (anteprima), `POST /projects/{p}/definitions/sync` (tutto, o `only` gli elementi scelti; vedi [definitions](../../definitions.md)) |
| Copilot | `GET /copilot/status[?project=]` (CLI, coding agent, prompt e modelli da scegliere con prezzo e costo medio per turno), `GET /copilot-sessions/{id}/turns` (uso per turno e totale), `GET /observability/copilot/turns[?limit=&project=]`, `GET /observability/copilot/models[?days=&project=]`, `GET/POST/DELETE /projects/{p}/copilot-sessions` (POST con `prepare`: i repository da preparare prima, `[{repository, branch, base}]`, 409 se «Prepara sviluppo» fallisce; o `learned: {automation_id, fields}`, un'automation imparata dall'Operatore, 409 se fallisce; DELETE `?task_note=`: le sessioni di un task), `GET/DELETE /copilot-sessions/{id}`, `GET/POST /copilot-sessions/{id}/messages`, `POST /copilot-sessions/{id}/approve`, `POST /copilot-sessions/{id}/answer` (la risposta alla domanda che Copilot fa durante l'esecuzione, tool MCP `ask_user`; 409 senza domanda in attesa), `POST /copilot-sessions/{id}/send-back` (un task «da verificare» rimandato a Copilot con un messaggio), `POST /copilot-sessions/{id}/save-note` (la risposta di un task che lavora solo in piano diventa una nota collegata), `POST /copilot-sessions/{id}/cancel` |
| Admin | `GET /admin/config`, `GET /observability/runs`, `GET /observability/runs/{run_id}/trace`, `GET /observability/tool-calls`, `GET/POST /admin/backups`, `GET /admin/backups/{nome}` |

## Convenzioni

- **Service da `Depends`**: `service: ProjectService = Depends(project_service)`. I provider in `dependencies.py` restituiscono i service del Container creato all'avvio (`app.state.container`).
- **Request e response** stanno in [`models/controller/`](../models/README.md): i modelli di dominio non escono mai dai controller.
- **Errori**: i controller non li gestiscono. Un `AppError` sollevato da un service diventa lo status HTTP giusto in `core/app.py` (404, 400, 409, 502) con il messaggio in `detail`; i dati rifiutati da un modello di dominio diventano 400; un body malformato è il 422 di FastAPI.
- **Nomi negli URL**: i nomi dei progetti e degli agenti finiscono nei path, quindi non possono contenere `/` o `\`.
- **File**: l'upload è il body grezzo di un `PUT` (niente multipart), il download restituisce i byte.
- **Automation**: `steps` + `edges` (`source`, `target`, `condition`, `value`; `source` può essere `input`); `edges` vuoto = la catena degli step. `fields` (nomi) e `purpose` (`""` o `prepare`); uno step `tool` ha `tool_name` e i suoi argomenti in `params`.
- **Streaming**: non ancora. `POST /conversations/{id}/messages` aspetta la risposta intera dell'agente.

## Aggiungere un endpoint

1. Request e response in `models/controller/<ambito>.py`.
2. La route in `controller/<ambito>_controller.py`; un ambito nuovo è un file nuovo con il suo `APIRouter`.
3. Se serve un service nuovo, il suo provider in `dependencies.py`.
4. L'`include_router` in `router.py`.
5. Rigenera il client del frontend: `npm run gen:api` in `web/` (i tipi vengono dall'OpenAPI).

## Test

In `test/unit/api/`: `test_projects_api.py`, `test_agents_api.py`, `test_project_areas_api.py` (chat, dati, git, automation, Atlassian, admin). Usano `TestClient` sull'app vera con un Container sugli store in memoria e agenti finti.
