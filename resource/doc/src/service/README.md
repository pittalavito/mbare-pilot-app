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
  chat_route_service.py     cache dei chatbot: messaggio simile → automation, senza agente
  atlassian_service.py      sito Jira + Confluence di un progetto
  backup_service.py         export del DB in SQL nella cartella di backup
  masking_service.py        mascheramento dei dati sensibili verso i modelli
  copilot_service.py        agent task delegati a GitHub Copilot CLI: chat di preparazione, esecuzione nel worker
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

- **Automation a grafo**: gli step sono i **nodi**, i **collegamenti** dicono quale output entra in quale step e a quale condizione. Ogni grafo parte dal nodo `input` (l'input della run). Un collegamento ha una condizione sul testo dell'output di partenza: `always`, `contains` / `not_contains` (testo, senza maiuscole), `matches` (regex), `otherwise` (nessuna delle altre condizioni dello stesso nodo). Le regole stanno in `domain/pipeline/graph.py`: nomi unici e diversi da `input`, niente cicli, ogni step raggiungibile da `input`, al massimo un `otherwise` per nodo e solo accanto a condizioni sul testo, `{nodo:Nome}` solo per uno step che precede. Un'automation salvata **senza collegamenti** è la catena dei suoi step, nell'ordine.
- **`PipelineService`**: crea e modifica le automation validando ogni step e il grafo (modello usabile, tool esistenti, agente della Libreria o del progetto, funzione e parametri validi), mette le run in coda, cancella lo storico, riceve l'heartbeat dei worker (`heartbeat`, `workers`, `worker_stopped`).
- **`PipelineRunner`**: prende la run più vecchia in coda e percorre il grafo in ordine topologico, **uno step alla volta**. Quando uno step finisce si valutano i suoi collegamenti in uscita: `contains` / `not_contains` (testo, senza maiuscole), `matches` (regex), `otherwise` (se nessuna condizione sul testo è passata), `always`. Uno step gira se almeno un collegamento in ingresso è passato; altrimenti è registrato come **saltato** (`skipped`), e così a cascata. Il suo `{input}` è l'output dell'unico ingresso passato, o tutti gli ingressi passati uniti come `## <step>` + output; `{nodo:Nome}` è l'output di quello step (vuoto se saltato). L'output della run è quello degli ultimi step eseguiti (uniti allo stesso modo se più d'uno). Il primo step che fallisce fa fallire la run. All'avvio del worker segna come fallite le run rimaste a metà (`fail_interrupted`).

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

### Cache: `ChatRouteService`

L'utente mette in cache un **suo** messaggio scegliendo un'automation del progetto e un input fisso (`add(messaggio, automation, input)`). Da lì, `send` confronta ogni messaggio con le voci del chatbot: se uno è abbastanza simile (`CHAT_ROUTE_THRESHOLD`, coseno 0..1, default 0,9) lancia **direttamente** l'automation, **senza l'agente** (niente LLM né token), e risponde `⚡ Ho lanciato l'automation X (id N).`. L'automation poi gira nel worker con i suoi step e tool, come sempre.

- **Similarità**: coseno degli embedding (`domain/client/embedding`), calcolato in Python sulle voci del chatbot (sono poche). L'embedder si sceglie con `CHAT_ROUTE_EMBEDDER`:
  - `hashing`: finto, stesse parole (senza maiuscole, accenti, articoli e preposizioni) = simili, sinonimi no;
  - `openrouter/<modello>` (es. `openrouter/openai/text-embedding-3-small`): un modello vero via OpenRouter, con `OPENROUTER_API_KEY`. Il testo esce dal PC, quindi viene **mascherato** con la mappa del progetto prima di partire, come per un LLM; senza `MaskingService` il servizio non si crea.
- **Stessi valori**: una voce è candidata solo se il messaggio nomina gli stessi valori sensibili, cioè gli stessi alias una volta mascherato (`REPO_7`, `PERSONA_2`, ...; `aliases_in` in `domain/masking/masker.py`). Serve perché un embedding trova «stato git di REPO_3» più vicino a «stato git di REPO_7» di qualunque sua riformulazione (misurato: 0,955 contro 0,67-0,73), e l'input della voce è fisso: senza la regola lancerebbe l'automation per il repository sbagliato. Vale anche al contrario: un messaggio con un valore che la voce non ha (o senza quello che la voce ha) va all'agente. Gli alias si calcolano con la mappa attuale, quindi una voce segue anche i valori aggiunti dopo. Senza `MaskingService` la regola non si applica.
- **Cambio di embedder**: una voce fatta con un altro embedder viene ricalcolata dal suo testo al primo confronto e salvata. La cache resta valida.
- **Log**: ogni confronto scrive nel log dell'API le similarità migliori (fino a 3), la soglia e la decisione, es. `Cache chatbot 1 · «git status di REPO_7» · voce 3=0.812, voce 5=0.955 (altri valori), voce 1=0.401 · soglia 0.80 → voce 3, lancio l'automation`. Il messaggio nel log è mascherato; «(altri valori)» segna le voci escluse dalla regola dei valori. Servono a scegliere `CHAT_ROUTE_THRESHOLD`: con un embedder vero le frasi equivalenti hanno similarità più basse di 1, quindi la soglia va tarata guardando i log.
- **Se l'embedding fallisce** (rete, chiave scaduta): la cache non viene consultata, risponde l'agente, e il log lo dice.
- **`!` all'inizio** del messaggio: salta la cache, risponde l'agente (in cache il messaggio va senza `!`).
- **Input fisso**: è lo stesso per ogni messaggio simile; le richieste con parametri che cambiano non vanno in cache.
- **Regole**: solo messaggi dell'utente, solo automation del progetto del chatbot, un messaggio una volta sola. La voce resta anche se si elimina la conversazione (il riferimento al messaggio diventa vuoto); se ne va con il chatbot o con l'automation.
- **Se l'automation non parte** (disattivata, senza step…) la risposta è un messaggio `error` che inizia con ⚡.
- **`hits`**: quante volte la voce ha risposto.

## Processi

**`ProcessService`**: il worker come processo che l'API avvia e ferma (il frontend nel browser non può avviare processi), e i log di API e worker.

- **Stato**: `running` se l'ha avviato l'app (file PID in `resource/run/worker.pid`), `external` se non l'ha avviato l'app ma un worker manda il suo heartbeat (da un terminale), `stopped` altrimenti.
- **Avvio**: con `WORKER_SCRIPT`, staccato dall'API (sopravvive ai suoi riavvii) e con il `.env` letto al momento; un worker avviato altrove non viene duplicato (409).
- `domain/process/manager.py`: `ProcessManager` (file PID con l'ora d'avvio, così un PID riusato non inganna; stop di tutto l'albero dei processi).

## Copilot

**`CopilotService`**: un agent task delegato a GitHub Copilot CLI ([client](../domain/client/copilot/README.md)) su un repository del progetto. Una sessione (`copilot_session`, messaggi in `copilot_message`) vive in due fasi, sempre sulla **stessa sessione di Copilot**:

1. **Preparazione** (`planning`, nell'API, mentre l'utente aspetta). `start(progetto, nota del task, repository)` manda il primo turno: il markdown del task e la richiesta di leggere il codice, fare domande e proporre un piano, senza modificare niente. Poi `send(id, testo)`: un turno per messaggio, in modalità piano (sola lettura, la blocca il CLI).
2. **Esecuzione** (nel worker). `approve(id)` mette la sessione in coda (`queued`), segnalando come avviso i file già modificati nel repository. Il worker (`run_next`) riprende la conversazione in autopilot, senza commit.

- **HEAD prima e dopo**: se è cambiato (un commit malgrado i divieti), la sessione lo dice (`head_moved`) e non annulla niente: decide l'utente.
- **File cambiati**: il `git status` del repository a fine esecuzione.
- **Una esecuzione alla volta per repository**: le altre aspettano in coda (`claim_next` salta i repository occupati); la preparazione intanto si può fare.
- **Annullamento** (`cancel`): una sessione in coda non parte; una in esecuzione la ferma il worker, che legge `cancel_requested` ogni pochi secondi. Timeout: `COPILOT_EXECUTION_TIMEOUT_MINUTES` (esecuzione), `COPILOT_PLANNING_TIMEOUT_MINUTES` (un turno di preparazione).
- **Il task segue**: in corso durante l'esecuzione, fatto se va a buon fine, da fare altrimenti. L'esito resta nella sessione, non nella nota.
- Dopo un'esecuzione la chat può continuare (si torna in preparazione) e un nuovo ok fa partire un'altra esecuzione. `fail_interrupted()` all'avvio del worker chiude le esecuzioni rimaste a metà.
- Niente mascheramento: Copilot legge comunque il codice del repository.
- **Prompt e divieti**: dal coding agent della cartella dei dati (`global-coding-agent.yml`, con l'override `project/<slug>/coding-agent.yml`; [definizioni](../../definitions.md#coding-agent-global-coding-agentyml-coding-agentyml)), letto da `coding_agent(progetto)` a ogni `start` e a ogni avvio dell'esecuzione. Se manca o è rotto: `start` dà errore, un'esecuzione già in coda fallisce con il motivo. `coding_agent_or_error(progetto)` lo dice a `GET /copilot/status?project=`, insieme ai prompt e ai modelli tra cui scegliere.
- **Sessioni e task**: una sessione tiene solo il nome della nota del task (`task_note`, senza chiave esterna). Cancellare il task non la cancella: resta, e la chat funziona ancora; la scheda Copilot la segna «task eliminato». `delete_task_sessions(progetto, task)` cancella tutte le sessioni di un task con i loro messaggi, nessuna se una è in coda o in esecuzione (409). La UI la propone quando elimini il task. Cancellare il progetto le cancella a cascata. Non c'è scadenza; l'uso dei turni (`copilot_turn`) resta sempre, e così la sessione di Copilot in `~/.copilot`.
- **Uso per turno** (observability): dopo ogni turno `_record_usage` salva una riga in `copilot_turn` con progetto, task, fase (`plan` o `execute`), modello, esito, durata e l'uso del turno. Il CLI riporta i totali della sessione: l'uso del turno è quanto sono cresciuti rispetto alla somma dei turni già registrati (se un totale cala, Copilot ha ricominciato a contare e vale tutto). Un turno fermato prima di scrivere il file registra zero, e il turno dopo recupera la differenza. Best effort: un errore qui non ferma la sessione. Le righe restano anche dopo aver cancellato la sessione. Letture: `session_turns(id)`, `recent_turns(limit, progetto)`, `usage_by_model(giorni, progetto)`.
- **Costi**: Copilot fattura in crediti AI (richieste premium sul piano legacy), non a token × prezzo: niente EUR, niente catalogo Modelli.
- **Modelli tra cui scegliere**: `model_options(definizione)` li ordina dal più economico (input + output; senza prezzo in fondo) e affianca a ognuno quanto ha usato finora in tutti i progetti (`copilot_usage_by_model`), per la media dei crediti per turno.
- **Cartella del task**: prima di ogni turno (preparazione ed esecuzione) `ProjectDataService.copilot_folder` ricompone `copilot/<sessione>/` con `task.md` e i riferimenti collegati (quelli che non esistono più si saltano) e Copilot la riceve con `--add-dir`. Al primo turno, se il task ha riferimenti, si aggiunge `references_prompt` con il percorso. Un task cancellato nel frattempo: niente cartella, la chat continua. Cancellare la sessione (o le sessioni del task) cancella anche la cartella.
- **Prompt e modello scelti**: `start(progetto, task, repository, prompt, model)`. `prompt` è uno dei `coding-agent/<nome>.md` (`""` = `plan_prompt`) e serve solo per il primo turno. `model` è uno dei `models:` (`""` = `COPILOT_MODEL`) e vale per ogni turno, esecuzione compresa. Entrambi restano salvati nella sessione; un valore fuori elenco è un errore.
- **Costruzione**: il Container chiama `CopilotService.from_config(...)`, che crea il `CopilotClient` e i timeout dalle impostazioni `COPILOT_*`. Dipende da `GitService` per la cartella del repository (controllata), l'HEAD prima e dopo e il `git status`; da `ProjectDataService` per il task e il suo stato.

## Definizioni da file

**`DefinitionService.sync(progetto)`**: applica a un progetto i file YAML di `definition/`: agenti globali e del progetto, il chatbot del progetto (o quello globale), le automation del progetto più quelle globali che non ridefinisce. Cerca per nome; il file vince sulle modifiche da UI, quello che non è nei file resta. Usa gli stessi servizi (e quindi le stesse validazioni) della UI; un file con errori viene saltato e segnalato. Formato e regole in [definitions](../../definitions.md).

## Atlassian

**`AtlassianService`**: un sito Jira + Confluence **per progetto** (tabella `project_atlassian`), sopra i [client Atlassian](../domain/client/atlassian/README.md). Testato con risposte finte, non ancora su un sito vero.

- **Impostazioni**: URL del sito (`https://…`), email, API token, progetto Jira e spazio Confluence predefiniti (facoltativi). Il token è salvato **cifrato** con `SecretBox`; un token vuoto al salvataggio tiene quello già salvato. Se la chiave di cifratura cambia, il token non si legge più e il progetto risulta non configurato.
- **`site(progetto)`** → `AtlassianSite`: il punto unico per usare Jira e Confluence di quel progetto (`check_connection`, issue, ricerca JQL, spazi, pagine, ricerca testo). Viene ricostruito quando cambiano le impostazioni. Senza configurazione: `ValidationError` che dice dove impostarla.
- **Copia nei riferimenti** (`reference_from_issue`, `reference_from_page`): l'issue (titolo `CHIAVE · sommario`, poi tipo, stato, priorità, assegnatario e la descrizione) o la pagina (titolo e testo) diventa un **riferimento di contesto** con `source` `jira` o `confluence` e il link all'originale, collegato agli agent task e alle todo list scelti (`ProjectDataService.import_reference`). Ricopiarla **aggiorna** il riferimento (stesso link) invece di duplicarlo; se il nome è preso da un riferimento con un altro link: 409.
- **Preferiti** (`list_favorites`, `add_favorite`, `remove_favorite`): issue Jira e pagine Confluence salvate come preferite **per progetto** (tabella `atlassian_favorite`), con chiave o id, titolo e link come erano al salvataggio: elencarli non chiama Atlassian. Aggiungere un preferito che c'è già restituisce quello salvato. Ogni preferito ricorda il **sito** a cui appartiene: salvando le impostazioni con un sito diverso, i preferiti degli altri siti vengono cancellati (stesso sito = restano, anche dopo aver rimosso e rimesso le impostazioni). Spariscono anche insieme al progetto.
- **Input validati prima di ogni richiesta**: chiavi di progetto (`PROJ`), di issue (`PROJ-123`) e di spazio, id di pagina, JQL e testo non vuoti. Le chiavi omesse usano i predefiniti del progetto.

## Mascheramento

**`MaskingService`**: i valori sensibili di un progetto (nomi dei repository, persone, email, altri termini) non arrivano mai al modello: al loro posto riceve un **alias** stabile (`REPO_1`, `PERSONA_2`, `EMAIL_1`, `TERMINE_3`), e nella risposta l'alias torna il valore vero.

- **Mappa per progetto, permanente**, su Redis (keyspace `mask`). Un valore ha sempre lo stesso alias; un alias tolto non viene mai riusato. Rimuovere il progetto cancella la sua mappa.
- **Come si riempie**:
  - **repository del progetto**: all'inizio di ogni run di un progetto vengono registrati tutti (gli stessi del tab Git), quindi sono mascherati già dal primo messaggio;
  - **dagli step funzione delle automation**: i campi marcati nel loro `FunctionResult`, registrati da `PipelineRunner` (`register_declared`) prima degli step agente che seguono;
  - **dagli output dei tool**: i campi marcati come sensibili nel modello di output (`MaskRepositoryName`, `MaskPersonName`, `MaskEmailAddress`, ...) vengono registrati da `AgentMask`; i tool non registrano nulla;
  - **a mano**: da **Impostazioni → Mascheramento dei dati**, per persone, clienti, altri termini. Minimo 3 caratteri.
- **Dove si applica**: tutto il mascheramento sta in **`AgentMask`** (`domain/agent/masking.py`), che `AgentService` usa per ogni run (chat, automation e chatbot, solo con una sessione quando la run è di un progetto):
  - la domanda e la cronologia della conversazione sono **mascherate** prima di arrivare al modello (`input`, `history`);
  - i tool ricevono gli argomenti **smascherati** (lavorano sui valori veri) e il loro output, serializzato, esce **mascherato** (`wrap`);
  - la risposta è **smascherata** prima di essere salvata e mostrata (`answer`).
- **Chi ci lavora**: i servizi non conoscono la sessione. `MaskingService` tiene la mappa, `MaskSession` la usa in una run; il resto del codice passa da `AgentMask`.
- **Regole**: maiuscole e minuscole indifferenti, solo parole intere (`api` non tocca `rapid`), i valori più lunghi vincono su quelli che contengono.
- **Cosa resta in chiaro**: la run salvata ha input e output veri; il trace in Redis (tool call e chiamate del modello) contiene invece quello che il modello ha visto, cioè gli alias. Un valore che non è un repository e che il modello vede prima che qualcuno lo registri passa in chiaro: per i nomi noti in anticipo (persone, clienti), aggiungili a mano.

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

In `test/unit/service/`: `test_store_service`, `test_model_service`, `test_agent_config_service`, `test_agent_scope` (globali e di progetto), `test_activation` (disattivazioni), `test_agent_service`, `test_git_service`, `test_pipeline` (definizioni, coda, esecuzione, heartbeat), `test_function_steps`, `test_pipeline_graph` (grafo salvato ed eseguito: rami, unioni, step saltati), `test_project_service`, `test_project_data_service`, `test_chatbot_service`, `test_chat_route_service` (cache: lancio senza agente, `!`, soglia, embedder, cosa si può mettere in cache), `test_atlassian_service`, `test_backup_service`, `test_masking` (mascheratore, mappa su Redis, giro completo in una run). Gli agenti sono finti (`FakeAgent`), il DB è SQLite in memoria e Redis è fakeredis: le fixture stanno in `test/conftest.py`.
