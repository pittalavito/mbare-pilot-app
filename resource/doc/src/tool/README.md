# `src/tool`

I tool che un agente può chiamare durante una run:

| Tool | Tipo | Cosa fa |
|---|---|---|
| `hello_world` | **statico**: non usa nulla della run | saluta il nome che riceve (esempio) |
| `git_status` | **con contesto**: usa i service e il progetto della run | branch, push/pull e file modificati di un repository del progetto (esempio) |
| `git_pull_fast_forward` | **con contesto** | aggiorna un repository del progetto dal remoto, solo in fast-forward |
| `git_stash` | **con contesto** | mette da parte le modifiche non committate di un repository del progetto |
| `git_stash_apply` | **con contesto** | riapplica uno stash (che resta nella lista) |
| `list_automations` | **con contesto**, solo chatbot | le automation del progetto che si possono lanciare adesso (attive, con step), con la descrizione |
| `run_automation` | **con contesto**, solo chatbot | lancia un'automation del progetto in background e riporta l'id dell'esecuzione |
| `automation_status` | **con contesto**, solo chatbot | stato di un'esecuzione di un'automation del progetto e dei suoi step: solo gli stati, niente output né messaggi d'errore |
| `read_context` | **con contesto** | il contesto del progetto per il chatbot: i `.md` di `projects/<slug>/chat-bot/` tranne `system-prompt.md`; ultima risorsa |

```
src/tool/
  registry.py           TOOL_REGISTRY (tutti i tool, per nome) e build_tools()
  spec.py               ToolSpec (nome, descrizione, builder) e static()
  context.py            ToolContext: quello che un tool può usare durante la run
  list/
    hello_world.py      esempio statico
    automation/
      run_automation.py lancia un'automation del progetto
      automation_status.py  stato di un'esecuzione
      list_automations.py   automation lanciabili del progetto
    project/
      read_context.py   contesto del progetto per il chatbot
    git/
      git_status.py     esempio con contesto
      git_pull_fast_forward.py  pull solo in fast-forward
      git_stash.py      stash delle modifiche locali
      git_stash_apply.py  riapplica uno stash
      params.py         argomenti dei tool git come li vede il modello
      errors.py         errori dei tool git restituiti all'agente
```

Gli output dei tool sono modelli in `models/domain/tool.py` (`HelloWorldResponse`, `GitStatusResponse`, `ToolErrorResponse`), serializzati in JSON.

## Come funziona

```
avvio:  TOOL_REGISTRY ──sync──► tabella tool (catalogo: nome + descrizione)
UI:     un agente / chatbot / step sceglie i tool dal catalogo, per nome
run:    AgentService ──build_tools(nomi, ToolContext)──► tool datapizza ──► agente
```

- **I tool stanno sopra i service**: un tool usa i service (es. `GitService`) attraverso il `ToolContext`, mai il Container.
- **Solo chatbot**: una `ToolSpec` con `chatbot_only=True` (`list_automations`, `run_automation`, `automation_status`) funziona solo nelle run del chatbot; `/tools` lo riporta (`chatbot_only`, calcolato dal codice, non salvato) e la UI la propone solo nel form del chatbot.
- **Catalogo**: all'avvio il registry viene copiato nella tabella `tool`. Un tool tolto dal codice resta nel catalogo con `available = False`: non si può più scegliere, e gli agenti che lo usano non partono finché non lo tolgono.
- **`build_tools(nomi, context)`**: costruisce i tool scelti per una run, nell'ordine dato; `ValidationError` se un nome non ha implementazione.

## `ToolContext`

Creato da `AgentService` per ogni run:

- `project_name`: il progetto della run (`None` fuori da un progetto);
- i service che i tool possono usare: `git`, `pipelines` (`PipelineService`, per le automation), `project_data` (`ProjectDataService`, per il contesto del chatbot);
- `origin`: cosa ha avviato la run (chat, automation, manuale): i tool delle automation funzionano solo con `chat`, cioè nel chatbot;
- `mask`: il mascheramento della run (solo nelle run di un progetto). Un tool che legge valori sensibili li registra con `context.register_sensitive(MaskCategory.X, valore)`: da lì in poi il modello vede l'alias.

**Mascheramento**: `build_tools` avvolge ogni tool (su una copia, perché i tool statici sono condivisi) così che riceva gli argomenti smascherati e restituisca l'output mascherato. Il tool non deve fare niente, tranne registrare i valori sensibili che legge (vedi [service](../service/README.md#mascheramento)).

`require_project()` restituisce il progetto o solleva un `ValidationError`: per i tool che hanno senso solo dentro un progetto.

**Il progetto lo decide la run, non il modello**: `git_status` riceve dal modello solo `repository`, e lo cerca sempre dentro il progetto della run. Un agente di un progetto non può leggere i repository di un altro.

## Automation: `run_automation(automation, input)`

Il chatbot mette in coda un'esecuzione di un'automation del progetto e risponde **subito** con `{automation, run_id, status: "queued"}`: non aspetta la fine. L'automation la esegue il worker, il risultato si vede nel tab Automation.

- **Quali**: le automation del progetto che si possono lanciare (attive e con almeno uno step). L'elenco lo dà `list_automations`: `run_automation` lancia solo per nome, e a un nome sconosciuto risponde con quelli disponibili.
- **Senza conferma**: il chatbot le lancia da solo.
- **Chi può usarlo**: solo il **chatbot** di un progetto (run con origine `chat`, `chatbot_run()`), come `automation_status`. Non un agente lanciato a mano né uno step **dentro un'automation** (potrebbe rilanciarla all'infinito), né una run fuori da un progetto: lì il tool non elenca niente e risponde con un errore.
- **Errori** (automation sconosciuta, con l'elenco di quelle disponibili; automation non valida): tornano all'agente come `{"error": ...}`.

## Pull: `git_pull_fast_forward(repository)`

Uno dei tool git che **modificano** il repository (con `git_stash` e `git_stash_apply`). Fa `git pull --ff-only` del branch corrente dal suo upstream:

- **mai un merge**: se il branch locale ha commit che il remoto non ha, si ferma e lo dice (serve un merge o un rebase fatto a mano);
- **rifiuta** con modifiche non committate ai file tracciati (le elenca), con HEAD staccato o con un branch senza upstream; i file nuovi non tracciati non lo bloccano;
- **risposta**: branch, upstream, `updated` e i commit arrivati (dal più recente);
- **mascheramento**: autori ed email dei commit arrivati vengono registrati (`PERSONA_n`, `EMAIL_n`).

Usa le credenziali git del PC senza chiederne (niente prompt): se il remoto chiede una password che non è salvata, il pull fallisce con l'errore di git. Timeout: 120 s.

## Stash: `git_stash(repository, message)`

`git stash push`: mette da parte le modifiche non committate ai **file tracciati**, lasciando pulita la cartella di lavoro (es. prima di `git_pull_fast_forward`, che con modifiche locali rifiuta).

- i file nuovi non tracciati **restano** dove sono;
- `message` vuoto → `mbare-pilot <data ora>`;
- se non c'è niente da mettere da parte risponde `stashed: false` e non crea uno stash vuoto;
- risposta: `ref` (`stash@{0}`), il messaggio e i file messi da parte.

## Stash apply: `git_stash_apply(repository, stash)`

`git stash apply`: riapplica uno stash. **Lo stash resta nella lista** (a differenza di `pop`), quindi non si perde niente.

- `stash`: `stash@{n}` oppure `n`; vuoto = l'ultimo (`stash@{0}`). Se non esiste, l'errore elenca quelli disponibili;
- **rifiuta** con modifiche non committate ai file tracciati, per non mescolarle con lo stash;
- **conflitti** (lo stash tocca file cambiati dopo da un commit): git li lascia nella cartella di lavoro, il tool risponde `applied: false` con l'elenco dei file in conflitto; si risolvono a mano, lo stash è ancora lì;
- risposta: lo stash applicato, il suo messaggio, i file cambiati.

## Errori restituiti all'agente

I tool git non interrompono la run quando qualcosa va storto: restituiscono un JSON `{"error": "..."}` con il problema e i repository disponibili (`errors.py`), così l'agente può correggersi e riprovare.

I messaggi di git e di `GitService` contengono percorsi locali: negli errori la cartella del progetto diventa `<progetto>` e la home dell'utente `~` (`hide_local_paths`, con `\` o `/`, senza distinguere maiuscole e minuscole). Il modello non vede mai dove sta il codice sul PC; i nomi dei repository vengono poi mascherati come in ogni output.

## Argomenti (`params.py`)

Ogni argomento ha tipo e descrizione con `Annotated`: è quello che il modello legge. Tutti obbligatori, con `''` per "non usato": così lo schema funziona anche in strict mode di OpenAI.

## Aggiungere un tool

**Statico** (non usa nulla della run):

```python
# tool/list/<nome>.py
from datapizza.tools import tool

@tool
def nome(arg: str) -> str:
    """Descrizione per il modello."""
    return Risposta(...).model_dump_json()
```

e in `registry.py` → `static(nome)`.

**Con contesto** (usa service o progetto): un file con `build(context) -> Tool` che definisce il tool dentro e lo restituisce, più la `ToolSpec(name, description, build)`; in `registry.py` → la spec. Se serve un service nuovo, va aggiunto a `ToolContext` e passato da `AgentService`.

In entrambi i casi: il modello di output in `models/domain/tool.py`.

## Test

- `test/unit/tool/test_registry.py`: registry per nome, ogni tool si costruisce con nome e descrizione, ordine di `build_tools`, nome sconosciuto, `require_project`.
- `test/unit/tool/test_hello_world.py`
- `test/unit/tool/test_run_automation.py`: run messa in coda con risposta immediata, solo automation attive e con step nella descrizione, automation sconosciuta, niente lancio fuori dal chatbot di un progetto (run manuale, fuori da un progetto, dentro un'automation, anche eseguita davvero dal runner).
- `test/unit/tool/test_automation_status.py`: solo gli stati dell'esecuzione e degli step, mai output o errori; esecuzioni di altri progetti non trovate; solo nel chatbot.
- `test/unit/tool/test_read_context.py`: i `.md` di `chat-bot/` senza il system prompt; errori senza file o senza progetto.
- `test/unit/tool/test_git_write.py`: pull e stash con un remoto vero: commit arrivati, già aggiornato, modifiche locali che bloccano, file non tracciati che non bloccano, branch divergente mai unito, branch senza upstream, autori registrati per il mascheramento, errori senza percorsi locali; stash dei soli file tracciati, stash e poi pull, niente da mettere da parte; stash apply dell'ultimo o di uno indicato (lo stash resta), errori (nessuno stash, stash inesistente o non valido, modifiche locali), conflitti segnalati.
- `test/unit/tool/test_git_tools.py`: `git_status` su un repository vero; progetto deciso dalla run, errori con i repository disponibili, percorsi fuori dal progetto, run senza progetto, schema degli argomenti, percorsi locali nascosti negli errori. Serve `git` nel PATH.

Usano `StoreService` e `GitService` sugli store in memoria di `test/conftest.py`.
