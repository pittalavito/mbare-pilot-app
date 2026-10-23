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
  atlassian_service.py      sito Jira + Confluence di un progetto
  backup_service.py         export del DB in SQL nella cartella di backup
```

Chi crea i service e li collega tra loro è il [Container](../core/README.md) (`core/container.py`): ogni service riceve nel costruttore quelli che usa.

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

## Atlassian

**`AtlassianService`**: un sito Jira + Confluence **per progetto** (tabella `project_atlassian`), sopra i [client Atlassian](../domain/client/atlassian/README.md). Testato con risposte finte, non ancora su un sito vero.

- **Impostazioni**: URL del sito (`https://…`), email, API token, progetto Jira e spazio Confluence predefiniti (facoltativi). Il token è salvato **cifrato** con `SecretBox`; un token vuoto al salvataggio tiene quello già salvato. Se la chiave di cifratura cambia, il token non si legge più e il progetto risulta non configurato.
- **`site(progetto)`** → `AtlassianSite`: il punto unico per usare Jira e Confluence di quel progetto (`check_connection`, issue, ricerca JQL, spazi, pagine, ricerca testo). Viene ricostruito quando cambiano le impostazioni. Senza configurazione: `ValidationError` che dice dove impostarla.
- **Preferiti** (`list_favorites`, `add_favorite`, `remove_favorite`): issue Jira e pagine Confluence salvate come preferite **per progetto** (tabella `atlassian_favorite`), con chiave o id, titolo e link come erano al salvataggio: elencarli non chiama Atlassian. Aggiungere un preferito che c'è già restituisce quello salvato. Ogni preferito ricorda il **sito** a cui appartiene: salvando le impostazioni con un sito diverso, i preferiti degli altri siti vengono cancellati (stesso sito = restano, anche dopo aver rimosso e rimesso le impostazioni). Spariscono anche insieme al progetto.
- **Input validati prima di ogni richiesta**: chiavi di progetto (`PROJ`), di issue (`PROJ-123`) e di spazio, id di pagina, JQL e testo non vuoti. Le chiavi omesse usano i predefiniti del progetto.

## Backup

**`BackupService`**: esporta tutto il DB Postgres come file SQL (`pg_dump` eseguito nel container Postgres con `docker exec`, quindi niente da installare sul PC) in `<BACKUP_DIR>/db/mbare-pilot-db-<data>-<ora>.sql`. `BACKUP_DIR` vuoto = la cartella `mbare-pilot-back-up` accanto al progetto.

- **Da UI**: Admin → Backup («Esporta il DB», elenco degli export, download).
- **Da terminale**: `python resource/scripts/export-db.py` (serve Postgres acceso, non l'API).
- **Ripristino**: il dump ha `--clean --if-exists`, quindi si può caricare su un DB esistente: `psql -U app -d app -f <file>.sql` (es. con `docker exec -i mbare-pilot-app-postgres psql -U app -d app < <file>.sql`).
- Il token Atlassian nel dump è **cifrato**: per usarlo dopo un ripristino serve la stessa `MBARE_PILOT_SECRET_KEY`.
- Non usa il Container: lo costruisce lo script direttamente dalla `Config`.

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

In `test/unit/service/`: `test_store_service`, `test_model_service`, `test_agent_config_service`, `test_agent_scope` (globali e di progetto), `test_activation` (disattivazioni), `test_agent_service`, `test_git_service`, `test_pipeline` (definizioni, coda, esecuzione, heartbeat), `test_function_steps`, `test_project_service`, `test_project_data_service`, `test_chatbot_service`, `test_atlassian_service`, `test_backup_service`. Gli agenti sono finti (`FakeAgent`), il DB è SQLite in memoria e Redis è fakeredis: le fixture stanno in `test/conftest.py`.
