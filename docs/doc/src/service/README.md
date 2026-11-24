# `src/service`

Le regole dell'app. Un servizio riceve gli store e gli altri servizi dal `Container` (`core/container.py`), non li costruisce mai. I controller chiamano i servizi; i servizi chiamano `domain/` e gli store. Gli errori sono quelli di `core/error.py`: il controller li trasforma in status HTTP.

## Store (`service/store/`)

Uno store per aggregato, costruiti una volta in `stores.py` sugli stessi backend. Fuori dallo store escono solo modelli di dominio: le righe e i record restano dentro (mapper in `domain/store/*/`).

| Store | Cosa tiene | Backend |
|---|---|---|
| `ProjectStore` | progetti e loro impostazioni | Postgres |
| `AgentStore` | ruoli, prompt versionati, agenti della Libreria | Postgres |
| `CatalogStore` | modelli (con prezzi) e tool | Postgres |
| `ChatbotStore` | chatbot, conversazioni, messaggi, cache delle automation | Postgres |
| `PipelineStore` | automation, step, archi, run | Postgres |
| `CopilotStore` | sessioni di Copilot, messaggi, turni (anche la coda del worker) | Postgres |
| `PlanStore` | piano di ogni attività | Postgres |
| `RagStore` | indice del contesto (documenti e pezzi, pgvector) | Postgres |
| `RunStore` | run degli agenti: fatti in Postgres, trace in Redis | Postgres + Redis |
| `EvaluationStore`, `WipStore`, `EmbeddingUsageStore`, `ToolRequestStore`, `AtlassianStore` | valutazioni, Elabora WIP, costi degli embedding, richieste di tool, sito Atlassian (token cifrato) | Postgres |
| `MaskStore`, `WorkerStore` | mappe del masking, heartbeat dei worker | Redis |
| `ProjectFileStore`, `DefinitionStore` | file dei progetti; definizioni a due livelli (app e cartella dati) | file |

## Progetti e dati

- **`ProjectService`**: apre una cartella esistente o ne crea una nuova (sempre dentro `PROJECT_ROOTS`), elenca, aggiorna, rimuove. Un progetto nuovo riceve i chatbot di default.
- **`ProjectDataService`**: i dati del progetto fuori dal codice, in `<MBARE_PILOT_HOME>/project/<slug>/`: note (anche tipate: attività, agent task, riferimenti), file caricati, contesto (un documento si trova senza badare alle maiuscole: `sviluppo.md` legge anche `Sviluppo.md`), cartelle di lavoro di Copilot senza repository. Collega task, voci e riferimenti; spunta una voce quando il suo task diventa fatto.
- **`GitService`**: git in sola lettura sulla cartella del progetto o su un repository dentro.
- **`CodeSearchService`**: ricerca libera nei file che git conosce (salta binari, file grandi, non UTF-8); salva una ricerca come riferimento codice.
- **`SavedSearchService`**: ricerche salvate. Default in `code-search/searches.yml`, quelle del progetto in `Project.code_searches`; «✨ Regex» chiama l'agente `regex`.
- **`RepositoryMapService`**: la mappa dei repository in `context/repository.md` («➕ Nuovo» → «🗺 Mappa dei repository», poi «🗺 Rigenera» dal documento).

## Agenti e chatbot

- **`AgentConfigService`**: ruoli, prompt versionati, catalogo dei tool, agenti. Valida ogni scrittura (ruolo esistente, prompt del ruolo, tool implementati).
- **`AgentService`**: esegue un agente con i suoi tool, il masking e il tracing; registra la run.
- **`StructuredAgentService`**: agenti con risposta strutturata (`output:`), una chiamata con lo schema di `STRUCTURED_OUTPUTS`; con tool, pochi passi.
- **`ChatbotService`**: i chatbot del progetto, ognuno con il suo agente, conversazioni e messaggi.
- **`AutomationCacheService`**: «questa richiesta → quella automation»; un messaggio abbastanza simile lancia l'automation senza LLM.
- **`ModelService`**: catalogo dei modelli (Admin → Modelli); `require_usable_model` è il controllo che usano tutti.
- **`DefinitionService`**: agenti, chatbot e automation dai file YAML, a due livelli (app e cartella dati, vince per nome il secondo); allineamento all'avvio (che segnala i file con i nomi della struttura vecchia) e «Sincronizza da file». Vedi [definizioni](../../definitions.md).
- **`MaskingService`**: mappa del masking per progetto (repository, persone, email, termini) e anteprima di un testo mascherato.

## Attività

- **`ActivityDraftService`**: «📎 Parto da riferimenti». Una chiamata all'agente `bozza-attivita` con «Cosa vuoi fare» e i soli titoli scelti; non crea niente.
- **`WipService`**: «Elabora WIP», dal testo nuovo della nota WIP le proposte per le attività (agente `wip`).
- **`PlanService`**: il piano e il giro.
  - **Proposta**: il Pianificatore (agente `pianificatore`, con `search_context`) propone i task per le voci scoperte, ogni sviluppo con pre e post (passi, comandi, automation) secondo `context/sviluppo.md`.
  - **Creazione**: le proposte scelte diventano agent task «da fare», collegati a voci e attività.
  - **Percorso**: per ogni task i passi, ricavati dallo stato del task, dalla sessione di Copilot e dal piano. Sviluppo: Pre → Delega → Piano di Copilot → Esecuzione → Conferma → Post. Analisi, Confluence, Jira: Delega → Risposta (→ Pubblica).
  - **Giro** (`advance_all`, nel worker): parte con «▶️ Avvia». Al task corrente delega a Copilot, dà l'ok al piano con `auto_approve`, salta pre e post vuoti con `auto_skip_empty`. Si ferma dove serve l'utente; il task corrente è il primo non finito.
  - **Comandi**: pausa, opzioni (cambiano solo quelle mandate), riprova la delega, «Fatto» e «Salta» su pre e post, `pass_on` (il risultato di un task va al successivo).
- **`OperationService`**: «🤖 Automatico» di pre e post: i comandi (solo quelli permessi), poi l'automation, nel worker; il primo errore ferma.
- **`ActivityCloseService`**: step Chiudi (l'agente `imparato` propone cosa ricordare, in `context/imparato.md`), riapri, archivia (nota riassunto, via attività, task, bozze, piano, sessioni).
- **`TodayService`**: «📌 Oggi», senza LLM.

## Copilot

**`CopilotService`**: agent task delegati a GitHub Copilot CLI.

- **Preparazione**: chat a turni in modalità piano. Il primo turno è il prompt del coding agent con `{task}`; Copilot legge task e riferimenti dal server MCP dell'app (`read_task`, `list_references`, `read_reference`, `search_context`). Nel repository l'app non scrive niente.
- **Esecuzione**: con «Ok, parti» va in coda; il worker la esegue (una per repository), poi il task passa a «da verificare» (conferma o rimanda a Copilot). Copilot non fa mai commit.
- **Task senza codice** (analisi, Confluence, Jira): niente esecuzione; «Salva come nota» scrive `analisi-<task>.md` o la bozza `bozza-confluence-…`/`bozza-jira-…`.
- **Senza repository**: un task senza codice può lavorare in una cartella dei dati del progetto. Il repository si può cambiare finché la sessione non è mai stata eseguita.
- Ogni turno registra crediti AI e token (Osservabilità).

Collegati:
- **`PublishService`**: «📤 Pubblica» di una bozza su Confluence o Jira, con anteprima; poi il task è fatto e la bozza si cancella.
- **`CommandService`**: i comandi permessi del progetto; un comando fuori lista diventa una richiesta («Sempre», «Solo stavolta», «No»).
- **`DevChecksService`**: impostazioni dei test per repository (comando, ambito) e l'Operatore del progetto.
- **`MavenService`**: allineamento dei `pom.xml` a un parent e coverage JaCoCo del codice nuovo.

## Automation

- **`PipelineService`**: automation come grafi di step (agente, agente della Libreria, tool) con archi condizionati, validate al salvataggio; anche in YAML (`domain/pipeline/yaml_format.py`). `enqueue` mette una run in coda.
- **`PipelineRunner`**: il worker esegue una run alla volta, step dopo step in ordine topologico.
- **`LearnService`**: da una run dell'Operatore a un'automation, senza LLM («✅ Giusto: fanne un'automation»).
- **`ToolRequestService`**: richieste di tool che l'Architetto scrive e Claude Code lavora dal server MCP dev; le istruzioni per Claude da `coding-agents/claude/tool-requests.md`.

## Contesto e Atlassian

- **`RagService`**: indice del contesto per progetto (pgvector): i documenti di `context/`, le attività chiuse e il contesto generale delle definizioni (`general/<nome>.md`). Si reindicizza quando un documento cambia; a parità di punteggio vince il progetto.
- **`AtlassianService`**: sito Jira e Confluence del progetto. Issue, pagine, cartelle, ricerche, preferiti, copia come riferimento, scelta di dove pubblicare.

## Osservabilità e amministrazione

- **`RunService`**: run degli agenti, tool chiamati, trace e «🔍 Cosa ha visto il modello» (mascherato e in chiaro).
- **`MetricsService`**: pagina Metriche: costi e tempi per agente e modello, Copilot, embedding.
- **`EvaluationService`**: valutazioni (Elabora WIP, RAG) sui set di `resource/eval`, nel worker o da terminale.
- **`ProcessService`**: il worker avviato e fermato dall'API, i log.
- **`BackupService`**: export del DB in `<BACKUP_DIR>/db/` (default `local/backups/db/`).
- **`RoadmapService`**: la bacheca da `board/roadmap.yml`; la UI la scrive nella cartella dati (testata, schede nuove, modificate, spostate, eliminate; ogni scheda con un `id` stabile).

## Test

`test/unit/service/` e `test/unit/api/`, con i fake di `test/fakes.py` (modelli strutturati) e `test/fake_copilot.py` (Copilot CLI). Il Copilot vero non parte mai nei test.
