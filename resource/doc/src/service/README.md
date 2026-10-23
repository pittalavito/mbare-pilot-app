# `src/service`

I servizi applicativi: le regole dell'app (validazioni, permessi tra progetti, versioni, coda) sopra lo store e i client di [`domain`](../domain/README.md). Controller e worker parlano solo con i service.

```
src/service/
  store_service.py          StoreService: unica porta verso Postgres, Redis e file
  model_service.py          catalogo dei modelli LLM (Admin → Modelli)
  chat_service.py           client LLM per modello, in cache
  agent_config_service.py   ruoli, prompt versionati, catalogo tool, agenti
  agent_service.py          esegue un agente e registra la run
  git_service.py            git sui repository di un progetto
  project_data_service.py   note e file di un progetto
  pipeline_service.py       automation: definizioni, coda, worker attivi
  pipeline_runner.py        esegue le run in coda (lo usa il worker)
  project_service.py        progetti                               (in arrivo)
  chatbot_service.py        chatbot e conversazioni                (in arrivo)
  atlassian_service.py      sito Jira + Confluence di un progetto  (in arrivo)
```

Chi crea i service e li collega tra loro è il Container (`core/container.py`, in arrivo): ogni service riceve nel costruttore quelli che usa.

## `StoreService`

La facciata unica della persistenza: crea tutti i repository (Postgres, Redis, file) dalla `Config` e parla solo in **modelli di dominio**, convertendo con gli Adapter/Factory di ogni store. Nei test riceve un engine SQLite in memoria e fakeredis.

Fa anche due cose trasversali: cifra e decifra il token Atlassian con `SecretBox`, e calcola i costi delle run dai prezzi del catalogo.

## Il motore delle automation

```
UI «Esegui» ──► PipelineService.enqueue ──► pipeline_run (queued)
                                                │
worker ──► PipelineRunner.run_next ──► claim (running) ──► step dopo step ──► done / failed
                                                         ├─ AGENT          → AgentService.run_definition
                                                         ├─ AGENT_CONFIG   → AgentService.run
                                                         └─ FUNCTION       → function/ (senza LLM)
```

- **`PipelineService`**: crea e modifica le automation validando ogni step (modello usabile, tool esistenti, agente della Libreria o del progetto, funzione e parametri validi), mette le run in coda, cancella lo storico, riceve l'heartbeat dei worker (`heartbeat`, `workers`, `worker_stopped`).
- **`PipelineRunner`**: prende la run più vecchia in coda, esegue gli step in ordine (l'output di uno diventa l'input del successivo tramite il template con `{input}` e `{pipeline_input}`), registra ogni step e si ferma al primo che fallisce. All'avvio del worker segna come fallite le run rimaste a metà (`fail_interrupted`).

## Agenti

- **`AgentConfigService`**: ruoli, versioni dei prompt (immutabili; ruoli e versioni si disattivano, non si cancellano), catalogo dei tool sincronizzato dal codice, agenti globali o di progetto. `blocked_reason` dice perché un agente non può partire (ruolo o prompt disattivati, modello non usabile, tool non più implementati).
- **`AgentService`**: costruisce l'agente (client da `ChatService`, tool con il `ToolContext` della run), lo esegue dentro il tracing di datapizza e salva la run: fatti in Postgres, trace in Redis.
- **`ModelService`**: il catalogo dei modelli; `require_usable_model` è il controllo che ogni service fa prima di salvare o eseguire un agente.

## Dati e git del progetto

- **`GitService`**: trova i repository nella cartella del progetto (fino a 2 livelli) e ne legge log e status, senza mai uscire dalla cartella.
- **`ProjectDataService`**: note e file del progetto nello store file, con i nomi validati da `domain/project/data_paths`.

## Test

In `test/unit/service/`: `test_store_service`, `test_model_service`, `test_agent_config_service`, `test_agent_scope` (globali e di progetto), `test_activation` (disattivazioni), `test_agent_service`, `test_git_service`, `test_pipeline` (definizioni, coda, esecuzione, heartbeat), `test_function_steps`. Gli agenti sono finti (`FakeAgent`), il DB è SQLite in memoria e Redis è fakeredis: le fixture stanno in `test/conftest.py`.
