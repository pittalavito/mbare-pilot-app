# `src/tool`

I tool che un agente può chiamare durante una run:

| Tool | Tipo | Cosa fa |
|---|---|---|
| `hello_world` | **statico**: non usa nulla della run | saluta il nome che riceve (esempio) |
| `git_status` | **con contesto**: usa i service e il progetto della run | branch, push/pull e file modificati di un repository del progetto (esempio) |
| `ask_agent` | **con contesto** | delega una domanda a un altro agente e ne riporta la risposta |
| `run_automation` | **con contesto** | lancia un'automation del progetto in background e riporta l'id dell'esecuzione |

```
src/tool/
  registry.py           TOOL_REGISTRY (tutti i tool, per nome) e build_tools()
  spec.py               ToolSpec (nome, descrizione, builder) e static()
  context.py            ToolContext: quello che un tool può usare durante la run
  list/
    hello_world.py      esempio statico
    agent/
      ask_agent.py      delega a un altro agente
    automation/
      run_automation.py lancia un'automation del progetto
    git/
      git_status.py     esempio con contesto
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
- **Catalogo**: all'avvio il registry viene copiato nella tabella `tool`. Un tool tolto dal codice resta nel catalogo con `available = False`: non si può più scegliere, e gli agenti che lo usano non partono finché non lo tolgono.
- **`build_tools(nomi, context)`**: costruisce i tool scelti per una run, nell'ordine dato; `ValidationError` se un nome non ha implementazione.

## `ToolContext`

Creato da `AgentService` per ogni run:

- `project_name`: il progetto della run (`None` fuori da un progetto);
- i service che i tool possono usare: `git`, `agents` (`AgentService`, per la delega), `pipelines` (`PipelineService`, per le automation);
- `depth`: il livello di delega della run (0 = chiesta dall'utente, 1 = chiesta da un altro agente);
- `origin`: cosa ha avviato la run (chat, automation, manuale, altro agente).

`require_project()` restituisce il progetto o solleva un `ValidationError`: per i tool che hanno senso solo dentro un progetto.

**Il progetto lo decide la run, non il modello**: `git_status` riceve dal modello solo `repository`, e lo cerca sempre dentro il progetto della run. Un agente di un progetto non può leggere i repository di un altro.

## Delega: `ask_agent(agent, question)`

Un agente chiede a un altro agente e riceve la sua risposta. È quello che serve a un chatbot orchestratore, che non legge le fonti ma delega agli specialisti.

- **A chi può chiedere**: agli agenti del progetto della run e a quelli globali (Libreria), solo quelli che possono partire adesso (niente ruolo o prompt disattivati, modello usabile). Fuori da un progetto, solo ai globali.
- **Come lo sa il modello**: l'elenco degli agenti disponibili, con la loro descrizione, è scritto nella descrizione del tool quando viene costruito per la run. La **descrizione di un agente** quindi conta: è quella che il modello legge per scegliere.
- **La domanda** deve essere completa: l'agente chiamato non vede la conversazione.
- **Run separata**: l'agente chiamato gira sullo stesso progetto ed è registrato a parte, con origine `agent` (Admin → Observability). La risposta torna come JSON `{agent, run_id, answer}`.
- **Un solo livello**: un agente chiamato con `ask_agent` non può delegare a sua volta (`MAX_DEPTH = 1`, profondità in `ToolContext.depth`).
- **Errori** (agente sconosciuto, con l'elenco di quelli disponibili; domanda vuota; agente che fallisce): tornano all'agente come `{"error": ...}`, la run non si interrompe.

## Automation: `run_automation(automation, input)`

Un agente mette in coda un'esecuzione di un'automation del progetto e risponde **subito** con `{automation, run_id, status: "queued"}`: non aspetta la fine. L'automation la esegue il worker, il risultato si vede nel tab Automation.

- **Quali**: le automation del progetto della run che si possono lanciare (attive e con almeno uno step), elencate con la loro descrizione nella descrizione del tool.
- **Senza conferma**: l'agente le lancia da solo.
- **Chi può usarlo**: solo un agente di un progetto chiamato dall'utente (chat, run manuale). Non un agente che gira **dentro un'automation** (potrebbe rilanciarla all'infinito), né uno chiamato da `ask_agent`, né una run fuori da un progetto: lì il tool non elenca niente e risponde con un errore.
- **Errori** (automation sconosciuta, con l'elenco di quelle disponibili; automation non valida): tornano all'agente come `{"error": ...}`.

## Errori restituiti all'agente

I tool git non interrompono la run quando qualcosa va storto: restituiscono un JSON `{"error": "..."}` con il problema e i repository disponibili (`errors.py`), così l'agente può correggersi e riprovare.

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
- `test/unit/tool/test_run_automation.py`: run messa in coda con risposta immediata, solo automation attive e con step nella descrizione, automation sconosciuta, niente lancio fuori da un progetto, da un agente delegato o da dentro un'automation (anche eseguita davvero dal runner).
- `test/unit/tool/test_ask_agent.py`: delega sullo stesso progetto con run registrata a parte, niente secondo livello di delega, agente sconosciuto, elenco degli agenti nella descrizione (solo quelli che possono partire, solo globali fuori da un progetto).
- `test/unit/tool/test_git_tools.py`: `git_status` su un repository vero; progetto deciso dalla run, errori con i repository disponibili, percorsi fuori dal progetto, run senza progetto, schema degli argomenti. Serve `git` nel PATH.

Usano `StoreService` e `GitService` sugli store in memoria di `test/conftest.py`.
