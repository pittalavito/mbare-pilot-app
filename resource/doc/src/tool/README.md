# `src/tool`

I tool che un agente può chiamare durante una run. Due tool di esempio, uno per tipo:

| Tool | Tipo | Cosa fa |
|---|---|---|
| `hello_world` | **statico**: non usa nulla della run | saluta il nome che riceve |
| `git_status` | **con contesto**: usa i service e il progetto della run | branch, push/pull e file modificati di un repository del progetto |

```
src/tool/
  registry.py           TOOL_REGISTRY (tutti i tool, per nome) e build_tools()
  spec.py               ToolSpec (nome, descrizione, builder) e static()
  context.py            ToolContext: quello che un tool può usare durante la run
  list/
    hello_world.py      esempio statico
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
- i service che i tool possono usare (oggi `git`).

`require_project()` restituisce il progetto o solleva un `ValidationError`: per i tool che hanno senso solo dentro un progetto.

**Il progetto lo decide la run, non il modello**: `git_status` riceve dal modello solo `repository`, e lo cerca sempre dentro il progetto della run. Un agente di un progetto non può leggere i repository di un altro.

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
- `test/unit/tool/test_git_tools.py`: `git_status` su un repository vero; progetto deciso dalla run, errori con i repository disponibili, percorsi fuori dal progetto, run senza progetto, schema degli argomenti. Serve `git` nel PATH.

Usano `StoreService` e `GitService` (in arrivo con i service).
