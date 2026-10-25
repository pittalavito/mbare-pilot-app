# `src/models`

Solo modelli dati (Pydantic / SQLModel), niente logica. Tre famiglie **separate**, una per livello: ognuna resta nel suo livello e si converte all'altra nei punti di passaggio.

```
src/models/
  domain/       il linguaggio dell'app: quello che service e domain si passano
  store/        com'è salvato: tabelle SQL, record Redis, file
  controller/   il contratto dell'API: request e response
```

```
API ── controller/* ──► controller ──► domain/* ──► service ──► domain/* ──► store ──► store/*
       (request/response)   from_x / to_x                       Factory / Adapter     (tabelle, record)
```

## Perché separati

- **Il DB può cambiare senza toccare l'API**, e viceversa: una colonna rinominata cambia solo `store/` e il suo Adapter/Factory.
- **Niente dati che escono per sbaglio**: le response elencano i campi uno per uno (es. il token Atlassian non c'è, c'è `has_token`).
- **Il dominio valida**: vincoli e default stanno nei modelli `domain/` (es. `ModelKey`, `max_steps` 1–50), quindi valgono ovunque, API o worker.

## `domain/`

| File | Modelli |
|---|---|
| `project.py` | `Project` (cartella su disco: `FOLDER` aperta o `SCRATCH` creata), `ProjectDataFile` (note e file del progetto) |
| `agent.py` | definizione: `AgentRole` → `SystemPrompt` (versioni immutabili) → `AgentConfig` (prompt + modello + tool); `AgentDefinition` (quello che serve per eseguire un agente, da config o da chatbot); run: `AgentRunRecord`, `RunTelemetry`, `TokenSummary`, `AgentRunSummary`, `ToolCallSummary` |
| `chat.py` | catalogo LLM: `ModelProvider`, `ChatModel` (prezzo per 1M token), `ModelKey` (`fornitore/modello`), `EmbeddingModelName` |
| `chatbot.py` | `Chatbot` (con il suo agente), `Conversation`, `ChatMessage`, `MessageRole`; cache: `ChatRoute` (messaggio → automation + input, con il suo embedding), `ChatRouteMatch` |
| `pipeline.py` | automation a grafo: `Pipeline` (step + collegamenti), `PipelineStep` (`AGENT`, `AGENT_CONFIG`, `FUNCTION`, con la posizione nel grafo), `PipelineEdge` con `EdgeConditionKind`, `StepAgent`; esecuzioni: `PipelineRun`, `PipelineStepRun`, `RunStatus` (con `skipped` per gli step non raggiunti); placeholder `{input}`, `{pipeline_input}`, `{nodo:Nome}`; il nodo `input` |
| `worker.py` | `WorkerStatus` (heartbeat del worker) |
| `definitions.py` | file YAML di agenti, chatbot e automation (`AgentFile`, `ChatbotFile`, `AutomationFile`, `StepFile`, `EdgeFile`, con `extra="forbid"`) e report della sincronizzazione (`SyncReport`, `SyncItem`); vedi [definitions](../../definitions.md) |
| `masking.py` | `MaskCategory` (repository, persona, email, termine), `MaskEntry` (valore ↔ alias) |
| `backup.py` | `BackupFile` (export del DB) |
| `git.py` | `GitRepository`, `GitCommit`, `GitStatus`, `GitChange` |
| `atlassian.py` | `AtlassianSettings` (token `SecretStr`), Jira (`JiraProject`, `JiraIssue`), Confluence (`ConfluenceSpace`, `ConfluencePage`, `ConfluenceSearchHit`), preferiti (`AtlassianFavorite`, `FavoriteKind`) |
| `tool.py` | output dei tool degli agenti, uno per tool (`AskAgentResponse`, `RunAutomationResponse`, `GitStatusResponse`, …) |

Tipi condivisi: `Name` (`agent.py`: stringa obbligatoria, ripulita, max 100) e `ModelKey` (`chat.py`: validata come `fornitore/modello`).

## `store/`

| File | Cosa |
|---|---|
| `db.py` | tabelle SQLModel (`*Table`). In testa c'è la mappa dello schema: tutto ruota attorno a `project`, e cancellare un progetto cancella a cascata quello che possiede. `project_name` NULL = globale. `pipeline_run` è anche la coda del worker; `chunk` ha l'embedding pgvector |
| `redis.py` | `AgentTraceRecord` (trace completo di una run), `WorkerHeartbeatRecord` (scade se il worker smette di battere) |
| `files.py` | `StoredFile`: chi chiama vede solo il `file_id`, il percorso resta dentro lo store |

Le righe non escono mai dallo store: le conversioni stanno in `domain/store/*/store.py` (`Factory` per scrivere, `Adapter` per leggere).

## `controller/`

Un file per ambito dell'API: `project`, `agent`, `chatbot`, `project_data`, `git`, `pipeline`, `atlassian`, `admin`.

- **Response** (`*Response`): con `from_<dominio>()` che le costruisce dal modello di dominio.
- **Request** (`*Request`, `*Body`): quello che l'API accetta; il controller le converte in modelli di dominio (es. `StepBody.to_step()`).
- La UI ne ha una **copia sua** in `ui/api_client/models.py`: le due vanno tenute allineate.

## Aggiungere un modello

1. **Dominio**: `domain/<ambito>.py`, con validazioni e default.
2. **Salvataggio**: la tabella in `store/db.py` (o il record in `store/redis.py`) + Factory/Adapter in `domain/store/`.
3. **API**: request/response in `controller/<ambito>.py`, e la copia lato UI.

## Dipendenze

`controller/pipeline.py` importa `function.spec.FunctionSpec` (per descrivere le funzioni degli step): è l'unico modello che dipende da un package fuori da `models/`.
