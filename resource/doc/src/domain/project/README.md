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
- **`note_type(nome)`**: il tipo di una nota dal suo nome: `agent-task-…` → agent task, `todo-list-…` → todo list, `code-reference-…` e `context-reference-…` → riferimenti, altrimenti generica.
- **`typed_note_file_name(tipo, titolo)`**: il nome di una nota tipizzata nuova, dal titolo (`agent-task-refactor-login.md`).
- **`data_file_name(nome)`**: il nome di un file caricato, senza cartelle davanti (`C:\x\report.pdf` → `report.pdf`).
- **Nomi rifiutati** (`ValidationError`): vuoti, `.` e `..`, che iniziano con `.`, con caratteri non validi su Windows (`< > : " / \ | ? *`). Così un nome non può mai uscire dalla cartella del progetto.

## Note tipizzate (`note_templates.py`)

Sul disco sono **note come le altre** (markdown in `notes/`); il tipo sta nel nome e il contenuto segue un template, che l'app mostra come form. Modelli in `models/domain/note.py` (`NoteType`, `AgentTask`, `TodoList`).

| Tipo | Nome | Template |
|---|---|---|
| Generica | qualsiasi altro | markdown libero |
| Agent task | `agent-task-<titolo>.md` | `# titolo`, `Stato: creato / in rifinitura / da fare / in corso / fatto`, `Tipo: rifinitura / sviluppo / analisi`, sezioni `## Obiettivo`, `## Contesto`, `## Criteri di accettazione` (checklist), `## Vincoli` |
| Todo list | `todo-list-<titolo>.md` | `# titolo` e voci `- [ ] testo  (alta, 2026-10-30)`: priorità (`alta`, `media`, `bassa`) e scadenza facoltative |
| Riferimento di codice | `code-reference-<titolo>.md` | `# titolo`, `Fonte: jira · <url>`, `Repository:`, `File:`, `Righe:`, sezione `## Contenuto` |
| Riferimento di contesto | `context-reference-<titolo>.md` | come il precedente, senza repository, file e righe |

- **Stato e tipo di un agent task** (`TaskStatus`, `TaskType` in `models/domain/note.py`): l'ordine è creato → in rifinitura → da fare → in corso → fatto. Creato a mano = «creato»; creato dal segretario (`create_agent_task`) = «in rifinitura»; a «da fare» (pronto da delegare) lo porti tu o il Refiner, con il tuo ok (il Refiner prende solo task «creati» e li porta «in rifinitura»); «in corso» e «fatto» li mette Copilot. `is_refined` vale da «da fare» in poi. Nella UI l'elenco è diviso per stato (i «Fatti» chiusi) e l'editor mostra il percorso con l'azione dello stato: «Rifinisci con il Refiner», «Segna da fare», «Delega a Copilot»; «Cambia stato» per il resto (ogni passaggio si salva subito, con il form). Il tipo (rifinitura di una storia, sviluppo, analisi) sceglie il prompt di Copilot (`type_prompts`, vedi [definizioni](../../../definitions.md)). Senza `Stato:` (o con uno sconosciuto) un task vale «creato»; senza `Tipo:` vale «sviluppo».
- `render_*` scrive il markdown, `parse_*` lo rilegge: lettura tollerante, perché il file si può modificare a mano. Righe sconosciute prima della prima sezione ignorate, sezioni mancanti vuote, il titolo mancante preso dal nome. Al salvataggio successivo resta solo quello che il template conosce. **Solo i titoli del template aprono una sezione** (`## Obiettivo`, `## Contenuto`…): ogni altro `## `, con quello che segue, è testo della sezione in cui si trova. Così il markdown con i suoi titoli (una issue Jira, una pagina Confluence copiata come riferimento, il contesto di un task) torna intero e non si perde al salvataggio.
- Il nome si decide alla creazione e non cambia più, anche se cambia il titolo.
- **Riferimenti e collegamenti**: agent task e todo list collegano i riferimenti per nome nella sezione `## Riferimenti` (`- code-reference-login.md`, scritta solo se ce ne sono), **molti a molti**: uno stesso riferimento può stare in più task e liste. `Fonte` dice da dove è stato copiato (vuota = scritto a mano; `jira`, `confluence`, `dynatrace`… per gli import). I riferimenti non compaiono tra le note generiche: si vedono solo dentro ciò che li collega (sezione «📎 Riferimenti» dell'editor). Si possono collegare solo note `code-reference-…` e `context-reference-…`; un nome che non esiste più (file cancellato a mano) è tollerato e segnato «non trovato».
- Servizio: `ProjectDataService.agent_tasks / create_agent_task / save_agent_task` e gli stessi per le todo list (409 se il nome esiste già, 400 se la nota è di un altro tipo). Si cancellano come note.
- Riferimenti: `references / reference / create_reference / save_reference`, `linked_from` (riferimento → chi lo collega) e `delete_reference`, che lo scollega anche da tutti i task e le liste. `import_reference` crea o aggiorna (stesso `source_url`) un riferimento copiato da fuori e `link_reference` lo collega: li usa la copia da Jira e Confluence.
- **Cosa mostra la scheda Dati** (⚙️ Impostazioni): una scelta per progetto (`Project.visible_note_types`, colonna JSON del progetto; `None` = `DEFAULT_VISIBLE_NOTE_TYPES`: note, agent task, todo list). Un tipo nascosto perde la sua sotto-scheda, i file restano. Mostrare i riferimenti aggiunge la sotto-scheda «📎 Riferimenti», con tutti quelli dei tipi scelti, anche non collegati. Servizio: `visible_note_types` / `save_visible_note_types`.

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
