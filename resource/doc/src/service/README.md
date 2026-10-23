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
  project_service.py        progetti: apri cartella, crea da zero, modifica, rimuovi
  chatbot_service.py        chatbot di un progetto, conversazioni e messaggi
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

## Chatbot

**`ChatbotService`**: i chatbot di un progetto. Ognuno ha il **suo agente**, configurato nel chatbot stesso (system prompt, modello, max steps, tool) e separato dagli agenti della Libreria.

- **Creare e modificare**: modello usabile, tool disponibili, nome unico nel progetto (senza distinguere maiuscole e minuscole). Se cambia il system prompt, sale `prompt_version`, così ogni run dice quale prompt ha risposto.
- **Conversazioni**: dalla più recente; eliminarne una elimina i suoi messaggi.
- **`send(conversazione, testo)`**: salva il messaggio dell'utente, esegue l'agente del chatbot con la conversazione precedente come memoria, **sul progetto del chatbot** (i tool git lavorano lì), e salva la risposta. Il primo messaggio diventa il titolo della conversazione (max 60 caratteri).
- **Se l'agente non risponde** (errore del modello, tool, modello disattivato…) la risposta è un messaggio di tipo `error`: si vede in chat ma non viene rimandato all'agente nei turni successivi.
- **Run registrate** come `chatbot/<nome>`, con ruolo `chatbot` e la versione del prompt: si trovano in Admin → Observability.

## Progetti

**`ProjectService`**: ogni percorso passa da `FolderBrowser`, quindi resta dentro `PROJECT_ROOTS`.

| Metodo | Cosa fa |
|---|---|
| `open_folder(nome, descrizione, cartella)` | registra una cartella che esiste già |
| `create_from_scratch(nome, descrizione, cartella_padre, nome_cartella)` | crea la cartella e registra il progetto; se il salvataggio fallisce, la cartella appena creata viene tolta |
| `update(nome, descrizione, embedding_model)` | le impostazioni modificabili; nome, origine e cartella restano fissi |
| `remove(nome)` | cancella il progetto dal DB, a cascata; la cartella del codice e quella dei dati restano sul disco |
| `folder_exists(progetto)` | la cartella c'è ancora? (la UI avvisa se è sparita) |

Un progetto nuovo viene rifiutato se il nome contiene `/` o `\` (finisce negli URL dell'API), se esiste già, se il suo slug coincide con quello di un altro progetto (le cartelle dei dati si chiamerebbero uguali) o se la cartella è già un altro progetto.

## Dati e git del progetto

- **`GitService`**: trova i repository nella cartella del progetto (fino a 2 livelli) e ne legge log e status, senza mai uscire dalla cartella.
- **`ProjectDataService`**: note e file del progetto nello store file, con i nomi validati da `domain/project/data_paths`.

## Test

In `test/unit/service/`: `test_store_service`, `test_model_service`, `test_agent_config_service`, `test_agent_scope` (globali e di progetto), `test_activation` (disattivazioni), `test_agent_service`, `test_git_service`, `test_pipeline` (definizioni, coda, esecuzione, heartbeat), `test_function_steps`, `test_project_service`, `test_project_data_service`, `test_chatbot_service`. Gli agenti sono finti (`FakeAgent`), il DB è SQLite in memoria e Redis è fakeredis: le fixture stanno in `test/conftest.py`.
