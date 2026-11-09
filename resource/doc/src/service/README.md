# `src/service`

I servizi applicativi: le regole dell'app (validazioni, permessi tra progetti, versioni, coda) sopra gli store e i client di [`domain`](../domain/README.md). Controller e worker parlano solo con i service.

```
src/service/
  store/                    gli store per aggregato: unica porta verso Postgres, Redis e file
  run_service.py            osservabilità: run, tool call e trace (Admin → Osservabilità)
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
  automation_cache_service.py     cache delle automation dei chatbot automation: messaggio simile → automation, senza agente
  atlassian_service.py      sito Jira + Confluence di un progetto
  backup_service.py         export del DB in SQL nella cartella di backup
  masking_service.py        mascheramento dei dati sensibili verso i modelli
  copilot_service.py        agent task delegati a GitHub Copilot CLI: chat di preparazione, esecuzione nel worker
```

Chi crea i service e li collega tra loro è il [Container](../core/README.md) (`core/container.py`): ogni service riceve nel costruttore **gli store e i service che usa, e solo quelli**. Così la firma dice cosa legge e scrive.

## Gli store (`service/store/`)

La persistenza è divisa per **aggregato**: uno store per gruppo di dati che vive e muore insieme. Ogni store crea i suoi repository e parla solo in **modelli di dominio**, convertendo con l'`Adapter`/`Factory` del suo aggregato (`domain/store/db/<aggregato>_mapper.py`, `domain/store/redis/<x>_mapper.py`). Fuori da uno store non circolano righe né record.

| Store | Cosa tiene | Backend | Chi lo usa |
|---|---|---|---|
| `RunStore` | run degli agenti: fatti (token, costi, tool call) e trace | Postgres + Redis | `AgentService` (scrive), `RunService` (legge) |
| `CatalogStore` | modelli LLM con i prezzi (`price_list`), modelli in uso, catalogo dei tool | Postgres | `ModelService`, `AgentConfigService`, `AgentService`, `ChatbotService`, `PipelineService` (`require_usable_model`) |
| `AgentStore` | ruoli, versioni dei prompt, agenti della Libreria e di progetto | Postgres | `AgentConfigService`, `DefinitionService`, `PipelineService` |
| `ProjectStore` | progetti | Postgres | quasi tutti: chi tocca i dati di un progetto controlla che esista |
| `ChatbotStore` | chatbot, conversazioni, messaggi, cache delle automation | Postgres | `ChatbotService`, `AutomationCacheService` |
| `PipelineStore` | automation (step, collegamenti) e run (step delle run); tiene l'engine per `transaction` | Postgres | `PipelineService`, `PipelineRunner` |
| `CopilotStore` | sessioni, messaggi e turni di Copilot (anche la coda del worker) | Postgres | `CopilotService` |
| `AtlassianStore` | sito e preferiti Atlassian; cifra e decifra il token con `SecretBox` | Postgres | `AtlassianService` |
| `WorkerStore` | heartbeat dei worker (con TTL) | Redis | `PipelineService` |
| `MaskStore` | mappe di mascheramento | Redis | `MaskingService`, `ProjectService` (rimozione) |
| `ProjectFileStore` | file dei progetti (`<data_home>/project`) | file | `ProjectDataService` |
| `DefinitionStore` | file delle definizioni (`<data_home>/definition`); rispetta `coding_agent.DefinitionFiles` | file | `DefinitionService`, `CopilotService` |

`Stores` (`store/stores.py`) li costruisce tutti una volta, sullo stesso engine e client Redis. Lo usano solo il Container e i test: nessun service riceve `Stores`.

I metodi che attraversano più aggregati stanno dove sta la domanda: `CatalogStore.model_keys_in_use` legge agenti, chatbot e step ma risponde «quali modelli non si possono eliminare»; i prezzi (`price_list`) per i costi delle run li legge `AgentService` dal catalogo.

**Nuovo store**: un modulo in `service/store/`, il mapper accanto ai repository del suo aggregato, l'attributo in `Stores`, la fixture in `test/conftest.py`, e il Container che lo passa ai service che lo usano.

## `RunService`

L'osservabilità di Admin: elenco delle run e delle tool call (dalla più recente) e trace di una run (`NotFoundError` se manca o è scaduta). Solo lettura: le run le scrive `AgentService` quando finiscono. I controller non usano mai uno store direttamente.

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
- **`AgentService`**: costruisce l'agente (client da `ChatService`, tool con il `ToolContext` della run), lo esegue dentro il tracing di datapizza e salva la run in `RunStore`: fatti in Postgres, trace in Redis. Riceve **sempre** `PipelineService`, `MaskingService`, `ProjectDataService` e `CopilotService`: se un tool può usarli in una run lo decide il tool (`ToolContext.require_*`, origine della run), non un argomento mancante. Un progetto senza mappa di mascheramento resta com'è.
- **`ModelService`**: il catalogo dei modelli e quelli in uso (`keys_in_use`, per Admin → Modelli); `require_usable_model(catalog, key)` è il controllo che ogni service fa prima di salvare o eseguire un agente.

## Chatbot

**`ChatbotService`**: i chatbot di un progetto, **più d'uno**. Ognuno ha il **suo agente**, configurato nel chatbot stesso (system prompt, modello, max steps, tool) e separato dagli agenti della Libreria.

- **Di default**: «Chat bot» (`automation`), «Refiner» (`refiner`) e «Segretario» (`secretary`), in `domain/chat/chatbots_default.py`, li crea `DefinitionService.seed_default_chatbots` nei progetti che non li hanno (per nome): all'avvio (`Container._seed_defaults`) e alla creazione di un progetto (`ProjectService`). Solo creati, mai aggiornati; un errore (es. modello non nel catalogo) va nel log, non ferma l'app. La UI non crea né elimina chatbot e ne cambia solo il modello: gli altri vengono dalle [definizioni](../../definitions.md).

- **Tipo** (`kind`): `automation` lancia le automation del progetto e ne controlla lo stato: i suoi tool sono **fissi** (`KIND_TOOLS`: `list_automations`, `run_automation`, `automation_status`), imposti dal codice al salvataggio e di nuovo a ogni messaggio, qualunque cosa dicano la UI, i file o il DB; ha la **cache delle automation**. `secretary` aiuta con le note: attività (legge, crea, ne cambia descrizione e stato, aggiunge voci e spunta), stato degli agent task e agent task nuovi (in rifinitura), tool fissi anche lui (`list_activities`, `read_activity`, `create_activity`, `update_activity`, `list_agent_tasks`, `list_references`, `create_agent_task`), niente cache; dei riferimenti vede solo i titoli. `refiner` rifinisce gli agent task: tool fissi (`create_code_reference`, `list_refinable_tasks`, `start_refinement`, `read_agent_task`, `update_agent_task`, `finish_refinement`), niente cache; prende un task solo «creato», lo lavora «in rifinitura» e lo porta a «da fare» con l'ok dell'utente, e la scansione del codice gli dà solo i conteggi; nella UI sta accanto agli agent task (Dati → Agent task), non nella scheda Chat. `custom` (il default): i tool li scegli tu, niente cache. Altri tipi (es. Copilot, contesto) si aggiungono a `ChatbotKind` e `KIND_TOOLS`.

- **Creare e modificare**: modello usabile, tool disponibili, nome unico nel progetto (senza distinguere maiuscole e minuscole). Se cambia il system prompt, sale `prompt_version`, così ogni run dice quale prompt ha risposto.
- **Cambiare solo il modello** (`set_model`, dalla UI): il resto resta com'è, compresa la versione del prompt; il modello deve essere del catalogo e attivo. Una sincronizzazione delle definizioni che contiene il chatbot rimette il modello del file.
- **Conversazioni**: dalla più recente; eliminarne una elimina i suoi messaggi.
- **`send(conversazione, testo)`**: salva il messaggio dell'utente, esegue l'agente del chatbot con la conversazione precedente come memoria, **sul progetto del chatbot** (i tool git lavorano lì), e salva la risposta. Il primo messaggio diventa il titolo della conversazione (max 60 caratteri).
- **Se l'agente non risponde** (errore del modello, tool, modello disattivato…) la risposta è un messaggio di tipo `error`: si vede in chat ma non viene rimandato all'agente nei turni successivi.
- **Run registrate** come `chatbot/<nome>`, con ruolo `chatbot` e la versione del prompt: si trovano in Admin → Observability.

- **Nota aperta** (`send(..., open_note)`, `open_note` di `POST /conversations/{id}/messages`): la nota aperta accanto alla chat (il pannello del Refiner manda il task aperto nell'editor). L'agente la riceve in testa al messaggio (`with_open_note`); nella conversazione resta il messaggio come l'hai scritto, e la cache non la usa.

### Cache delle automation: `AutomationCacheService`

Solo dei chatbot di tipo `automation` (`Chatbot.has_automation_cache`): negli altri non si consulta e non si può aggiungere una voce. Si chiama così perché altri tipi potranno avere cache diverse.

L'utente mette in cache un **suo** messaggio scegliendo un'automation del progetto e un input fisso (`add(messaggio, automation, input)`). Da lì, `send` confronta ogni messaggio con le voci del chatbot: se uno è abbastanza simile (`AUTOMATION_CACHE_THRESHOLD`, coseno 0..1, default 0,9) lancia **direttamente** l'automation, **senza l'agente** (niente LLM né token), e risponde `⚡ Ho lanciato l'automation X (id N).`. L'automation poi gira nel worker con i suoi step e tool, come sempre.

- **Similarità**: coseno degli embedding (`domain/client/embedding`), calcolato in Python sulle voci del chatbot (sono poche). L'embedder si sceglie con `AUTOMATION_CACHE_EMBEDDER`:
  - `hashing`: finto, stesse parole (senza maiuscole, accenti, articoli e preposizioni) = simili, sinonimi no;
  - `openrouter/<modello>` (es. `openrouter/openai/text-embedding-3-small`): un modello vero via OpenRouter, con `OPENROUTER_API_KEY`. Il testo esce dal PC, quindi viene **mascherato** con la mappa del progetto prima di partire, come per un LLM; senza `MaskingService` il servizio non si crea.
- **Stessi valori**: una voce è candidata solo se il messaggio nomina gli stessi valori sensibili, cioè gli stessi alias una volta mascherato (`REPO_7`, `PERSONA_2`, ...; `aliases_in` in `domain/masking/masker.py`). Serve perché un embedding trova «stato git di REPO_3» più vicino a «stato git di REPO_7» di qualunque sua riformulazione (misurato: 0,955 contro 0,67-0,73), e l'input della voce è fisso: senza la regola lancerebbe l'automation per il repository sbagliato. Vale anche al contrario: un messaggio con un valore che la voce non ha (o senza quello che la voce ha) va all'agente. Gli alias si calcolano con la mappa attuale, quindi una voce segue anche i valori aggiunti dopo. Senza `MaskingService` la regola non si applica.
- **Cambio di embedder**: una voce fatta con un altro embedder viene ricalcolata dal suo testo al primo confronto e salvata. La cache resta valida.
- **Log**: ogni confronto scrive nel log dell'API le similarità migliori (fino a 3), la soglia e la decisione, es. `Cache chatbot 1 · «git status di REPO_7» · voce 3=0.812, voce 5=0.955 (altri valori), voce 1=0.401 · soglia 0.80 → voce 3, lancio l'automation`. Il messaggio nel log è mascherato; «(altri valori)» segna le voci escluse dalla regola dei valori. Servono a scegliere `AUTOMATION_CACHE_THRESHOLD`: con un embedder vero le frasi equivalenti hanno similarità più basse di 1, quindi la soglia va tarata guardando i log.
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
- **Task non ancora pronto** (creato o in rifinitura): si delega comunque, ma il primo messaggio della chat è un avviso (`not_refined_warning`); `delegate_task` lo restituisce in `warning`, perché il chatbot lo dica.
- **Prompt del tipo**: senza un prompt scelto, `start` usa quello del tipo del task (`type_prompts`), altrimenti `plan_prompt`; la sessione salva il nome del prompt usato davvero.
- Dopo un'esecuzione la chat può continuare (si torna in preparazione) e un nuovo ok fa partire un'altra esecuzione. `fail_interrupted()` all'avvio del worker chiude le esecuzioni rimaste a metà.
- Niente mascheramento: Copilot legge comunque il codice del repository.
- **Prompt e divieti**: dal coding agent della cartella dei dati (`global-coding-agent.yml`, con l'override `project/<slug>/coding-agent.yml`; [definizioni](../../definitions.md#coding-agent-global-coding-agentyml-coding-agentyml)), letto da `coding_agent(progetto)` a ogni `start` e a ogni avvio dell'esecuzione. Se manca o è rotto: `start` dà errore, un'esecuzione già in coda fallisce con il motivo. `coding_agent_or_error(progetto)` lo dice a `GET /copilot/status?project=`, insieme ai prompt e ai modelli tra cui scegliere.
- **Sessioni e task**: una sessione tiene solo il nome della nota del task (`task_note`, senza chiave esterna). Cancellare il task non la cancella: resta, e la chat funziona ancora; la scheda Copilot la segna «task eliminato». `delete_task_sessions(progetto, task)` cancella tutte le sessioni di un task con i loro messaggi, nessuna se una è in coda o in esecuzione (409). La UI la propone quando elimini il task. Cancellare il progetto le cancella a cascata. Non c'è scadenza; l'uso dei turni (`copilot_turn`) resta sempre, e così la sessione di Copilot in `~/.copilot`.
- **Uso per turno** (observability): dopo ogni turno `_record_usage` salva una riga in `copilot_turn` con progetto, task, fase (`plan` o `execute`), modello, esito, durata e l'uso del turno. Il CLI riporta i totali della sessione: l'uso del turno è quanto sono cresciuti rispetto alla somma dei turni già registrati (se un totale cala, Copilot ha ricominciato a contare e vale tutto). Un turno fermato prima di scrivere il file registra zero, e il turno dopo recupera la differenza. Best effort: un errore qui non ferma la sessione. Le righe restano anche dopo aver cancellato la sessione. Letture: `session_turns(id)`, `recent_turns(limit, progetto)`, `usage_by_model(giorni, progetto)`.
- **Costi**: Copilot fattura in crediti AI (richieste premium sul piano legacy), non a token × prezzo: niente EUR, niente catalogo Modelli.
- **Modelli tra cui scegliere**: `model_options(definizione)` li ordina dal più economico (input + output; senza prezzo in fondo) e affianca a ognuno quanto ha usato finora in tutti i progetti (`copilot_usage_by_model`), per la media dei crediti per turno.
- **Cartella del task, nel repository**: prima di ogni turno (preparazione ed esecuzione) il servizio riscrive `<repository>/mbare-pilot/<nome del task>/` (`domain/project/task_folder.py`) con i file che dà `ProjectDataService.copilot_files`: `task.md` e quello che collega, cioè riferimenti e note per nome e i file caricati in `files/<nome>` (quelli che non esistono più si saltano). Il prompt dice solo dove sono (`{task_folder}`); Copilot non riceve altre cartelle (`--add-dir` è solo il repository). Al primo turno un errore di scrittura (es. `mbare-pilot` è un file) ferma la delega prima di salvare la sessione; nei turni dopo la cartella è best effort: un task cancellato nel frattempo lascia l'ultima copia e la chat continua. Per l'esecuzione la cartella si riscrive dopo aver messo il task «in corso». La cartella **resta** anche cancellando la sessione o le sessioni del task. `mbare-pilot/` è visibile a git ma esce dagli elenchi dell'app (`_changed_files`: avviso prima dell'esecuzione, file cambiati).
- **Prompt e modello scelti**: `start(progetto, task, repository, prompt, model)`. `prompt` è uno dei `coding-agent/<nome>.md` (`""` = `plan_prompt`) e serve solo per il primo turno. `model` è uno dei `models:` (`""` = `COPILOT_MODEL`) e vale per ogni turno, esecuzione compresa. Entrambi restano salvati nella sessione; un valore fuori elenco è un errore.
- **Costruzione**: il Container chiama `CopilotService.from_config(...)`, che crea il `CopilotClient` e i timeout dalle impostazioni `COPILOT_*`. Dipende da `GitService` per la cartella del repository (controllata), l'HEAD prima e dopo e il `git status`; da `ProjectDataService` per il task e il suo stato.

## Definizioni da file

**`DefinitionService.sync(progetto)`**: applica a un progetto i file YAML di `definition/`: agenti globali e del progetto, il chatbot del progetto (o quello globale), le automation del progetto più quelle globali che non ridefinisce. Cerca per nome; il file vince sulle modifiche da UI, quello che non è nei file resta. Usa gli stessi servizi (e quindi le stesse validazioni) della UI; un file con errori viene saltato e segnalato. Formato e regole in [definitions](../../definitions.md).

## Atlassian

**`AtlassianService`**: un sito Jira + Confluence **per progetto** (tabella `project_atlassian`), sopra i [client Atlassian](../domain/client/atlassian/README.md). Testato con risposte finte, non ancora su un sito vero.

- **Impostazioni**: URL del sito (`https://…`), email, API token, progetto Jira e spazio Confluence predefiniti (facoltativi). Il token è salvato **cifrato** con `SecretBox`; un token vuoto al salvataggio tiene quello già salvato. Se la chiave di cifratura cambia, il token non si legge più e il progetto risulta non configurato.
- **`site(progetto)`** → `AtlassianSite`: il punto unico per usare Jira e Confluence di quel progetto (`check_connection`, issue, ricerca JQL, spazi, pagine, ricerca testo). Viene ricostruito quando cambiano le impostazioni. Senza configurazione: `ValidationError` che dice dove impostarla.
- **Copia nei riferimenti** (`reference_from_issue`, `reference_from_page`): l'issue (titolo `CHIAVE · sommario`, poi tipo, stato, priorità, assegnatario e la descrizione) o la pagina (titolo e testo) diventa un **riferimento di contesto** con `source` `jira` o `confluence` e il link all'originale, collegato agli agent task e alle attività scelti (`ProjectDataService.import_reference`). Ricopiarla **aggiorna** il riferimento (stesso link) invece di duplicarlo; se il nome è preso da un riferimento con un altro link: 409.
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

**`ProjectService`**: ogni percorso passa da `FolderBrowser`, quindi resta dentro `PROJECT_ROOTS`. Un progetto nuovo riceve i chatbot di default (`DefinitionService.seed_default_chatbots`).

| Metodo | Cosa fa |
|---|---|
| `open_folder(nome, descrizione, cartella)` | registra una cartella che esiste già |
| `create_from_scratch(nome, descrizione, cartella_padre, nome_cartella)` | crea la cartella e registra il progetto; se il salvataggio fallisce, la cartella appena creata viene tolta |
| `update(nome, descrizione, embedding_model)` | le impostazioni modificabili; nome, origine e cartella restano fissi |
| `remove(nome)` | cancella il progetto dal DB, a cascata; la cartella del codice e quella dei dati restano sul disco |
| `folder_exists(progetto)` | la cartella c'è ancora? (la UI avvisa se è sparita) |

Un progetto nuovo viene rifiutato se il nome contiene `/` o `\` (finisce negli URL dell'API), se esiste già, se il suo slug coincide con quello di un altro progetto (le cartelle dei dati si chiamerebbero uguali) o se la cartella è già un altro progetto.

## Dati e git del progetto

- **`GitService`**: trova i repository nella cartella del progetto (fino a 2 livelli), senza mai uscire dalla cartella. Legge log, status, diff, branch e stash; cambia i repository solo con operazioni che non perdono niente: fetch, pull in fast-forward, stash e stash apply, checkout e nuovo branch (rifiutati se rischiano le modifiche locali), add + commit, push mai forzato, `pull_all_by_branch` (tutti i repository su un branch, saltando quelli che non si possono toccare) e `pull_repository_by_branch` (lo stesso per un solo repository). `unpushed_changes` (sola lettura): i commit di HEAD che nessun branch remoto ha e le righe che aggiungono ai file di un pathspec, contro ogni commit di confine (dopo un merge di un branch remoto restano solo le righe davvero nuove).
- **`MavenService`**: legge il `pom.xml` alla radice di ogni repository del progetto, dalla cartella di lavoro (il branch su cui è ogni repository, modifiche non committate comprese), e lo confronta con la versione di un POM parent del progetto (`parent_alignment`): indicato per `artifactId` o riconosciuto (il repository che gli altri nominano più spesso come `<parent>`); le proprietà dei microservizi si scelgono con un nome o un modello con `*`. Solo lettura; trova repository e cartelle con `GitService`, quindi non esce dalla cartella del progetto. La lettura del POM, senza I/O, è in `domain/maven/pom.py`: namespace ignorato, `groupId` e `version` ereditati dal parent, `${...}` risolti con le proprietà del POM stesso, `project.version` e `project.parent.version`; quello che il POM non definisce (es. una proprietà di un parent remoto) resta com'è. Le regole di ogni comando sono nella [documentazione dei tool](../tool/README.md).
  - **`new_code_coverage`**: la coverage JaCoCo delle righe non ancora pushate (`GitService.unpushed_changes`, solo `src/main/java`) per repository, dopo `parent_alignment` come cancello: `mvn` gira solo dove l'allineamento al parent è confermato (il parent stesso, le librerie sulla sua versione, i microservizi con le proprietà giuste); gli altri sono `NOT_ALIGNED` o `NOT_VERIFIABLE` con il motivo. Con il [client Maven](../domain/client/maven/README.md) scrive il `jacoco.xml` che manca o è più vecchio del `jacoco.exec` (l'unica scrittura del service, sotto `target/`), poi lo legge con `domain/maven/jacoco.py`. Esito per repository in `CoverageCheck` (`models/domain/maven.py`), testo nella funzione [`coverage_new_code`](../function/README.md).
- **`ProjectDataService`**: note e file del progetto in `ProjectFileStore`, con i nomi validati da `domain/project/data_paths`.

### Commenti `todoMbarePilot`: `CodeTodoService`

- **`scan(progetto)`**: per ogni repository del progetto legge i file che git conosce (`git ls-files --cached --others --exclude-standard`: i tracciati e i nuovi non ignorati, quindi `.gitignore` vale). Salta i file che non ci sono più, quelli oltre `MAX_FILE_BYTES` (1 MB), i binari (un byte NUL all'inizio), quelli non UTF-8 e `mbare-pilot/` (le cartelle dei task per Copilot). Restituisce i commenti per file, con percorsi relativi al progetto (`api/src/login.py`).
- **Il commento** (`domain/project/code_todos.py`): `todoMbarePilot{descrizione}` ovunque in una riga, in qualunque linguaggio; la descrizione è il testo tra le graffe, su quella riga (spazi ripetuti ridotti a uno, vuota = saltato). Più commenti sulla stessa riga contano tutti.
- **Scritti male** (`find_malformed`): quello che somiglia al marcatore ma non viene raccolto (`todo mbare pilot` in qualunque maiuscola e spaziatura) dice cosa non va: maiuscole diverse, spazio prima della `{`, `}` non chiusa sulla riga, descrizione vuota, niente `{…}` dopo. Finisce nella nota in «⚠️ Da correggere», con file, riga e la riga stessa, e nel conteggio `malformed`; anche da solo crea la nota, perché tu lo veda.
- **`save(progetto)`**: scrive la scansione nel riferimento codice `code-reference-todo-mbare-pilot.md` («TODO Mbare Pilot», `Fonte: todoMbarePilot`), **uno per progetto**: i commenti raggruppati per file (`### percorso`, poi `- riga N: descrizione`), con data e totali. Ogni scansione lo riscrive; il nome non cambia, quindi i collegamenti da task e attività restano. Senza commenti: la nota esistente lo dice, una nuova non si crea. Una nota con quel nome scritta a mano (altra `Fonte`) non si tocca: `ConflictError`. Restituisce solo i conteggi (`CodeTodoScan`).
- **Nella UI** «ⓘ» accanto al pulsante spiega come si scrive il commento (con esempi e «Copia il commento»); l'esito della scansione dice anche quanti sono da correggere.
- **Dalla UI, senza agente**: `POST /projects/{progetto}/code-todos` (409 se la nota è scritta a mano), il pulsante «🔍 Todo del codice» nella sezione Riferimenti di un task o di un'attività (collega la nota) e nella sotto-scheda Riferimenti (la apre). Il Refiner tiene il suo tool `create_code_reference`.

## Test

In `test/unit/service/`: `store/test_run_store`, `store/test_pipeline_store` (transazioni, numero di query), `test_run_service`, `test_model_service`, `test_agent_config_service`, `test_agent_scope` (globali e di progetto), `test_activation` (disattivazioni), `test_agent_service`, `test_git_service`, `test_pipeline` (definizioni, coda, esecuzione, heartbeat), `test_function_steps`, `test_pipeline_graph` (grafo salvato ed eseguito: rami, unioni, step saltati), `test_project_service`, `test_project_data_service`, `test_chatbot_service`, `test_automation_cache_service` (cache: lancio senza agente, `!`, soglia, embedder, cosa si può mettere in cache), `test_atlassian_service`, `test_backup_service`, `test_masking` (mascheratore, mappa su Redis, giro completo in una run). Gli agenti sono finti (`FakeAgent`), il DB è SQLite in memoria e Redis è fakeredis: le fixture stanno in `test/conftest.py`, una per store (`project_store`, `pipeline_store`, …, tutte da `stores`), quelle dei service più usati (`git_service`, `project_data_service`, `masking_service`, `pipeline_service`, `agent_config_service`) e `make_agent_service`, che costruisce un `AgentService` completo come il Container e prende i service che il test vuole guidare (es. un `ChatService` con un client finto).
