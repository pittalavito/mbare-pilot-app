# `src/domain/project`

Le regole sui file di un progetto: dove stanno i suoi dati, come si chiamano note e file, e quali cartelle del PC l'app può aprire.

```
src/domain/project/
  data_paths.py       percorsi e nomi dei dati del progetto (funzioni pure, niente disco)
  note_templates.py   i template delle note tipizzate: markdown da e verso i campi
  folder_browser.py   FolderBrowser: navigare e creare cartelle, solo dentro PROJECT_ROOTS
```

Un progetto ha **due posti** distinti:

| | Dove | Chi lo gestisce |
|---|---|---|
| **Codice** | la sua cartella sul PC (`root_path`), scelta con «Apri cartella» o creata con «Crea da zero» | `FolderBrowser` |
| **Dati** (note, file caricati, contesto) | `<MBARE_PILOT_HOME>/project/<slug>/{notes,files,context}`, fuori dal codice | `data_paths` + `ProjectDataService` |
| **Definizioni** (agenti, chatbot, automation in YAML) | `<MBARE_PILOT_HOME>/definition/` (globali e `project/<slug>/`) | `data_paths` + `DefinitionService`, vedi [definitions](../../../definitions.md) |

## Dati del progetto (`data_paths.py`)

Solo funzioni pure: decidono nomi e percorsi, non toccano il disco.

- **`project_slug(nome)`**: la cartella dei dati, minuscola e con `-` (`"My App"` → `my-app`).
- **`note_file_name(nome)`**: `"Setup"` o `"setup.md"` → `setup.md`. Le note sono sempre markdown.
- **`note_type(nome)`**: il tipo di una nota dal suo nome: `agent-task-…` → agent task, `todo-list-…` → todo list, altrimenti generica.
- **`typed_note_file_name(tipo, titolo)`**: il nome di una nota tipizzata nuova, dal titolo (`agent-task-refactor-login.md`).
- **`data_file_name(nome)`**: il nome di un file caricato, senza cartelle davanti (`C:\x\report.pdf` → `report.pdf`).
- **Nomi rifiutati** (`ValidationError`): vuoti, `.` e `..`, che iniziano con `.`, con caratteri non validi su Windows (`< > : " / \ | ? *`). Così un nome non può mai uscire dalla cartella del progetto.

## Note tipizzate (`note_templates.py`)

Sul disco sono **note come le altre** (markdown in `notes/`); il tipo sta nel nome e il contenuto segue un template, che l'app mostra come form. Modelli in `models/domain/note.py` (`NoteType`, `AgentTask`, `TodoList`).

| Tipo | Nome | Template |
|---|---|---|
| Generica | qualsiasi altro | markdown libero |
| Agent task | `agent-task-<titolo>.md` | `# titolo`, `Stato: da fare / in corso / fatto`, sezioni `## Obiettivo`, `## Contesto`, `## Criteri di accettazione` (checklist), `## Vincoli` |
| Todo list | `todo-list-<titolo>.md` | `# titolo` e voci `- [ ] testo  (alta, 2026-10-30)`: priorità (`alta`, `media`, `bassa`) e scadenza facoltative |

- `render_*` scrive il markdown, `parse_*` lo rilegge: lettura tollerante, perché il file si può modificare a mano. Righe sconosciute ignorate, sezioni mancanti vuote, il titolo mancante preso dal nome. Al salvataggio successivo resta solo quello che il template conosce.
- Il nome si decide alla creazione e non cambia più, anche se cambia il titolo.
- Servizio: `ProjectDataService.agent_tasks / create_agent_task / save_agent_task` e gli stessi per le todo list (409 se il nome esiste già, 400 se la nota è di un altro tipo). Si cancellano come note.

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
