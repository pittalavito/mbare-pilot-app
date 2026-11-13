# `src/domain/project`

Le regole sui file di un progetto: dove stanno i suoi dati, come si chiamano note e file, e quali cartelle del PC l'app può aprire.

```
src/domain/project/
  data_paths.py       percorsi e nomi dei dati del progetto (funzioni pure, niente disco)
  note_templates.py   i template delle note tipizzate: markdown da e verso i campi
  task_folder.py      il task e i suoi riferimenti come file nel repository, per Copilot (mbare-pilot/<task>/)
  code_todos.py       i commenti todoMbarePilot{…} del codice e la nota che diventano (vedi CodeTodoService)
  folder_browser.py   FolderBrowser: navigare e creare cartelle, solo dentro PROJECT_ROOTS
  coding_agent.py     prompt e divieti di Copilot dai file di definition/ (vedi definitions.md)
  wip.py              la nota WIP (wip.md): testo nuovo dopo l'ultimo segno, paragrafi, il segno (vedi WipService)
```

Un progetto ha **due posti** distinti:

| | Dove | Chi lo gestisce |
|---|---|---|
| **Codice** | la sua cartella sul PC (`root_path`), scelta con «Apri cartella» o creata con «Crea da zero» | `FolderBrowser` |
| **Dati** (note, file caricati, contesto) | `<MBARE_PILOT_HOME>/project/<slug>/{notes,files,context}`, fuori dal codice. La cartella del task per Copilot sta invece nel repository: `mbare-pilot/<nome del task>/` (`task_folder.py`) | `data_paths` + `ProjectDataService` |
| **Definizioni** (agenti, chatbot, automation in YAML) | `<MBARE_PILOT_HOME>/definition/` (globali e `project/<slug>/`) | `data_paths` + `DefinitionService`, vedi [definitions](../../../definitions.md) |

## Dati del progetto (`data_paths.py`)

Solo funzioni pure: decidono nomi e percorsi, non toccano il disco.

- **`project_slug(nome)`**: la cartella dei dati, minuscola e con `-` (`"My App"` → `my-app`).
- **`note_file_name(nome)`**: `"Setup"` o `"setup.md"` → `setup.md`. Le note sono sempre markdown.
- **`note_type(nome)`**: il tipo di una nota dal suo nome: `agent-task-…` → agent task, `attivita-…` → attività, `code-reference-…` e `context-reference-…` → riferimenti, altrimenti generica.
- **`typed_note_file_name(tipo, titolo)`**: il nome di una nota tipizzata nuova, dal titolo (`agent-task-refactor-login.md`).
- **`data_file_name(nome)`**: il nome di un file caricato, senza cartelle davanti (`C:\x\report.pdf` → `report.pdf`).
- **Nomi rifiutati** (`ValidationError`): vuoti, `.` e `..`, che iniziano con `.`, con caratteri non validi su Windows (`< > : " / \ | ? *`). Così un nome non può mai uscire dalla cartella del progetto.

## La nota WIP (`wip.py`)

`wip.md` è una nota generica, una per progetto, sempre **la prima** nella sotto-scheda «📝 Note» (anche prima di esistere: salvandola si crea). Testo libero; «📥 Elabora WIP» ([service](../../service/README.md#elabora-wip)) ne legge solo il **testo nuovo**, cioè quello dopo l'ultima riga `—— elaborato il 05/11 14:30 ——` (`pending`). Applicando le proposte, `with_sign` scrive il segno dopo i paragrafi elaborati (il resto resta nuovo) e riscrive i paragrafi elaborati separati da una riga vuota; il diario sopra l'ultimo segno resta com'è. `with_sign` restituisce `None` se il testo nuovo non comincia più con quello elaborato (la nota è cambiata nel frattempo).

## Note tipizzate (`note_templates.py`)

Sul disco sono **note come le altre** (markdown in `notes/`); il tipo sta nel nome e il contenuto segue un template, che l'app mostra come form. Modelli in `models/domain/note.py` (`NoteType`, `AgentTask`, `TodoList`).

| Tipo | Nome | Template |
|---|---|---|
| Generica | qualsiasi altro | markdown libero |
| Agent task | `agent-task-<titolo>.md` | `# titolo`, `Stato: creato / in rifinitura / da fare / in corso / da verificare / fatto`, `Tipo: sviluppo / analisi / doc confluence / task jira`, `Test: tutti / solo toccati` (facoltativo: i test della «Verifica sviluppo», senza = il default del progetto), sezioni `## Obiettivo`, `## Contesto`, `## Criteri di accettazione` (checklist), `## Vincoli` |
| Attività | `attivita-<titolo>.md` | `# titolo`, `Stato: da fare / in corso / fatta`, sezioni `## Descrizione`, `## Todo` (voci `- [ ] testo  (alta, 2026-10-30)  → agent-task-….md`: priorità `alta`, `media`, `bassa`, scadenza e task nato dalla voce facoltativi), `## Agent task` (i task nati da lei, per nome), `## Imparato` (facoltativa) |
| Riferimento di codice | `code-reference-<titolo>.md` | `# titolo`, `Fonte: jira · <url>`, `Repository:`, `File:`, `Righe:`, sezione `## Contenuto` |
| Riferimento di contesto | `context-reference-<titolo>.md` | come il precedente, senza repository, file e righe |

- **Stato e tipo di un agent task** (`TaskStatus`, `TaskType` in `models/domain/note.py`): l'ordine è creato → in rifinitura → da fare → in corso → da verificare → fatto. Creato a mano = «creato»; creato dal segretario (`create_agent_task`) = «in rifinitura»; «Rifinisci con il Refiner» lo porta da «creato» a «in rifinitura» (senza LLM); a «da fare» (pronto da delegare) lo porti tu o il Refiner, con il tuo ok; «in corso» lo mette Copilot. Uno **sviluppo** finito da Copilot va a «da verificare»: controlli le modifiche e lo **confermi** («fatto», solo lo stato: commit e push restano tuoi) o lo **rimandi a Copilot** con un messaggio (nuova esecuzione della stessa sessione, vedi [service](../../service/README.md#copilot)). Gli altri tipi non passano da «da verificare»: diventano «fatti» quando salvi la risposta di Copilot come nota. `is_refined` vale da «da fare» in poi. Nella UI l'elenco è diviso per stato (i «Fatti» chiusi) e l'editor mostra il percorso con l'azione dello stato: «Rifinisci con il Refiner», «Segna da fare», «Delega a Copilot», «Conferma» / «Rimanda a Copilot»; «Cambia stato» per il resto (ogni passaggio si salva subito, con il form). Senza `Stato:` (o con uno sconosciuto) un task vale «creato»; senza `Tipo:` vale «sviluppo».
- **I tipi** (`TaskType`): `development` (sviluppo: Copilot cambia il codice, preparazione poi esecuzione), `analysis` (analisi del codice), `confluence` (pagina Confluence), `jira` (rifinire una issue Jira). Gli ultimi tre lavorano **solo in piano** (`plan_only`): Copilot legge e risponde, e la risposta diventa una nota collegata al task (`analisi-<task>.md`, `bozza-<task>.md`). Il tipo sceglie anche il prompt di Copilot (`type_prompts`) e la checklist del Refiner (`task_checklists`), vedi [definizioni](../../../definitions.md). Il vecchio `Tipo: rifinitura` (rifinire una storia) si legge come `task jira`; il file si riscrive solo quando salvi il task.
- **Attività** (erano le «todo list»): lo stato lo scegli tu (o il segretario); quando tutte le voci sono fatte l'editor propone «Segna fatta». Gli agent task nati da un'attività sono scritti **solo nell'attività** (`## Agent task`): il task mostra «Nasce da» ricavandolo da lì; cancellare un task lo scollega (`delete_note`), cancellare un'attività lascia i suoi task. Nella UI (zona Lavoro) le attività vengono prima di «Tutti i task» e un agent task nato da un'attività si apre dentro di lei; dall'editor dell'attività si crea un task già collegato (l'attività si salva subito) o se ne collega uno esistente. **«Imparato»** (`learned`, sezione `## Imparato`, scritta solo se c'è): cosa hai imparato; un'attività **fatta** con «Imparato» entra nell'indice del contesto ([RAG](../../service/README.md#contesto-rag)), che il Refiner e Copilot consultano.
- **Task e voci** (blocco 08): una voce ricorda **un** task nato da lei (`TodoItem.agent_task`, la freccia `→ agent-task-….md` in fondo alla riga, dopo priorità e scadenza; una freccia verso altro resta testo). Il task di una voce sta anche in `## Agent task` (aggiunto al salvataggio). In **un punto solo**, `save_agent_task` (da UI, Copilot, Refiner, segretario): se il task arriva a «fatto» le sue voci si spuntano, se lo lascia si despuntano («da verificare» non conta); restituisce le voci toccate (`ItemChange`), che la UI notifica. Lo stato dell'attività non cambia mai da solo (con tutte le voci fatte va in «📌 Oggi» → «Da chiudere»). Cancellare il task toglie la freccia (la voce resta); cambiare il testo della voce non la tocca. Nell'editor dell'attività: accanto alla voce il badge con lo stato del task (apre il task) o il menu «🤖» che chiede il tipo e crea il task (`create_task_from_item`: «creato», titolo = testo della voce, contesto = voce, titolo e descrizione dell'attività, riferimenti dell'attività; controlla il testo della voce, 409 se è cambiata o ha già un task), poi lo apre. `link_item` collega un task esistente a una voce (lo usa il segretario).
- **Migrazione**: all'avvio (`Container._seed_defaults` → `migrate_todo_lists`) i file `todo-list-<titolo>.md` di ogni progetto diventano `attivita-<titolo>.md`: stesse voci e riferimenti, descrizione vuota, stato «fatta» se tutte le voci sono fatte, altrimenti «da fare». Se il nome nuovo è già preso la todo list resta com'è (nel log). Una vecchia todo list si legge comunque come attività (voci sotto il titolo, nessuno stato). Le impostazioni salvate con `todo_list` valgono come `activity`.
- `render_*` scrive il markdown, `parse_*` lo rilegge: lettura tollerante, perché il file si può modificare a mano. Righe sconosciute prima della prima sezione ignorate, sezioni mancanti vuote, il titolo mancante preso dal nome. Al salvataggio successivo resta solo quello che il template conosce. **Solo i titoli del template aprono una sezione** (`## Obiettivo`, `## Contenuto`…): ogni altro `## `, con quello che segue, è testo della sezione in cui si trova. Così il markdown con i suoi titoli (una issue Jira, una pagina Confluence copiata come riferimento, il contesto di un task) torna intero e non si perde al salvataggio.
- Il nome si decide alla creazione e non cambia più, anche se cambia il titolo.
- **Riferimenti e collegamenti**: agent task e attività collegano i riferimenti per nome nella sezione `## Riferimenti` (`- code-reference-login.md`, scritta solo se ce ne sono), **molti a molti**: uno stesso riferimento può stare in più task e attività. `Fonte` dice da dove è stato copiato (vuota = scritto a mano; `jira`, `confluence`, `dynatrace`… per gli import). I riferimenti non compaiono tra le note generiche: si vedono solo dentro ciò che li collega (sezione «📎 Riferimenti» dell'editor). Si possono collegare i riferimenti (`code-reference-…`, `context-reference-…`), le **note generiche** (per nome, `decisioni.md`) e i **file caricati** (`files/<nome>`, esattamente); non agent task né attività. Note e file collegati si collegano così come sono (niente copia): li riceve **solo Copilot**, con i tool MCP `list_references` e `read_reference` (`task_links`, `task_link_text`: una nota com'è, un file come testo UTF-8, uno binario con una riga che lo dice); Refiner e segretario lavorano solo sui riferimenti. Cancellare una nota o un file lo scollega da tutti i task e le attività. Un nome che non esiste più (file cancellato a mano) è tollerato e segnato «non trovato».
- Servizio: `ProjectDataService.agent_tasks / create_agent_task / save_agent_task`, gli stessi per le attività (`activities / activity / create_activity / save_activity`) e `link_agent_task` (409 se il nome esiste già, 400 se la nota è di un altro tipo); per le voci `create_task_from_item`, `link_item`, `item_index`. Si cancellano come note.
- Riferimenti: `references / reference / create_reference / save_reference`, `linked_from` (riferimento → chi lo collega) e `delete_reference`, che lo scollega anche da tutti i task e le attività. `import_reference` crea o aggiorna (stesso `source_url`) un riferimento copiato da fuori e `link_reference` lo collega: li usa la copia da Jira e Confluence.
- **Cosa mostra la zona Progetto** (🔧 Impostazioni; attività e agent task stanno sempre in Lavoro): una scelta per progetto (`Project.visible_note_types`, colonna JSON del progetto; `None` = `DEFAULT_VISIBLE_NOTE_TYPES`: note, agent task, attività). Un tipo nascosto perde la sua sotto-scheda, i file restano. Anche la sotto-scheda «📎 File» si può nascondere (`Project.files_visible`, colonna `files_visible`, vero di default): i file restano e si possono ancora collegare come riferimento. Mostrare i riferimenti aggiunge la sotto-scheda «📎 Riferimenti», con tutti quelli dei tipi scelti, anche non collegati. Servizio: `visible_note_types` / `save_visible_note_types`.
- **Test della «Verifica sviluppo»**: `Project.test_scope` (`all` / `touched`, colonna `test_scope`) e `Project.test_commands` (repository → comando, colonna JSON; senza = rilevato). Servizio: `test_scope`, `test_commands`, `test_command`, `save_test_settings`.
- **Giorni di «In scadenza»** del pannello «📌 Oggi»: `Project.due_soon_days` (colonna `due_soon_days`, default 3, da 0 a 60), nelle stesse impostazioni. Servizio: `due_soon_days` / `save_due_soon_days`.

## Cartelle del PC (`folder_browser.py`)

`FolderBrowser(roots)` lavora solo dentro le radici configurate (`PROJECT_ROOTS` nel `.env`, separate da `;`; vuoto = la home dell'utente). Fuori dalle radici non legge e non scrive niente.

| Metodo | Cosa fa |
|---|---|
| `resolve(path)` | il percorso assoluto, se esiste, è una cartella e sta dentro una radice; espande `~` e le variabili d'ambiente |
| `is_allowed(path)` | il percorso sta dentro una radice? |
| `parent(folder)` | la cartella sopra, `None` quando si è già su una radice |
| `subfolders(folder, show_hidden)` | le sottocartelle leggibili, in ordine alfabetico; quelle nascoste solo su richiesta |
| `create_folder(parent, name)` | crea `parent/name`; il nome deve essere valido e la cartella non deve esistere |

È quello che usa il selettore di cartelle della UI (`GET /folders`) e la creazione di un progetto da zero.

## Test

`test/unit/domain/project/test_folder_browser.py`: percorsi dentro e fuori dalle radici, cartelle mancanti, ordinamento e cartelle nascoste, risalita fino alla radice, creazione. Le regole di `data_paths` sono coperte dai test di `ProjectDataService`.
