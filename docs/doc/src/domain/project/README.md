# `src/domain/project`

Le regole sui file di un progetto: dove stanno i suoi dati, come si chiamano note e file, quali cartelle del PC l'app può aprire. Niente servizi qui: funzioni pure e classi piccole.

```
src/domain/project/
  data_paths.py       percorsi e nomi dei dati del progetto (niente disco)
  note_templates.py   le note tipizzate: markdown da e verso i campi
  folder_browser.py   FolderBrowser: navigare e creare cartelle, solo dentro PROJECT_ROOTS
  coding_agent.py     prompt, divieti e modelli di Copilot dalle definizioni
  code_search.py      la ricerca libera nel codice: pattern, glob, righe, riferimento
  repository_map.py   la mappa dei repository in context/repository.md
  wip.py              la nota WIP: il testo nuovo dopo l'ultimo segno
  links.py            il link a una nota nella sua zona (/work o /project)
```

## Dove stanno le cose

| | Dove |
|---|---|
| **Codice** | la cartella del progetto sul PC (`root_path`), dentro `PROJECT_ROOTS`. L'app non ci scrive niente: ci lavorano Copilot e i comandi permessi |
| **Dati** | `<MBARE_PILOT_HOME>/project/<slug>/`: `notes/`, `files/`, `context/`, `copilot/<task>/` (cartella di lavoro di Copilot senza repository) |
| **Definizioni** | `resource/definition/` (app) e `<MBARE_PILOT_HOME>/definition/` (le tue, anche per progetto): vedi [definizioni](../../../definitions.md) |

`data_paths.py`: `project_slug`, `note_file_name` (sempre `.md`), `note_type` (dal prefisso del nome), `typed_note_file_name`, `data_file_name`. Un nome vuoto, `.`/`..`, che inizia con `.` o ha caratteri non validi su Windows è rifiutato: un nome non esce mai dalla cartella.

## Note tipizzate (`note_templates.py`)

Sul disco sono note markdown come le altre; il tipo sta nel prefisso del nome e il contenuto segue un template, che la UI mostra come form. Modelli in `models/domain/note.py`.

| Tipo | Nome | Contenuto |
|---|---|---|
| Agent task | `agent-task-<titolo>.md` | `Stato:`, `Tipo:` (sviluppo, analisi, doc confluence, task jira), `Test:`, dove pubblicare (Confluence); `## Obiettivo`, `## Contesto`, `## Criteri di accettazione` (checklist), `## Vincoli`, `## Pre` e `## Post` (solo uno sviluppo), `## Riferimenti` |
| Attività | `attivita-<titolo>.md` | `Stato:`; `## Descrizione`, `## Todo` (voci con priorità, scadenza e `→ agent-task-….md`), `## Agent task`, `## Riferimenti` |
| Riferimento | `code-reference-<titolo>.md`, `context-reference-<titolo>.md` | `Fonte:`, per il codice `Repository:`, `File:`, `Righe:`; `## Contenuto` |
| Bozza e analisi | `bozza-confluence-…`, `bozza-jira-…`, `analisi-…` | la risposta di Copilot, markdown libero |
| Generica | qualsiasi altro | markdown libero |

- Stati di un task: creato → in rifinitura → da fare → in corso → da verificare → fatto. Quando un task diventa fatto, la sua voce nell'attività si spunta da sola.
- Pre e Post: `Automation: <nome>`, un punto per passo, un punto tra backtick per comando.
- La lettura è tollerante (il file si può modificare a mano): solo i titoli del template aprono una sezione, quindi il markdown con i suoi titoli resta intero; al salvataggio resta solo quello che il template conosce.
- Il nome si decide alla creazione e non cambia con il titolo. I riferimenti si collegano per nome, molti a molti.

## Cartelle del PC (`folder_browser.py`)

`FolderBrowser(roots)` lavora solo dentro `PROJECT_ROOTS` (separate da `;`, vuoto = la home): `resolve`, `is_allowed`, `parent`, `subfolders`, `create_folder`. Lo usano il selettore di cartelle (`/folders`) e la creazione di un progetto.

## La nota WIP (`wip.py`)

`wip.md`, una per progetto: testo libero. «Elabora WIP» legge solo il testo dopo l'ultimo segno e, applicate le proposte, aggiunge il segno in fondo.
