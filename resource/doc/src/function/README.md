# `src/function`

Le **funzioni** delle automation: codice Python che uno step esegue **senza LLM** (gratis e deterministico). Sono l'equivalente dei [tool](../tool/README.md), ma per gli step delle pipeline invece che per gli agenti.

| Funzione | Cosa fa | Parametri |
|---|---|---|
| `git_status` | branch, push/pull e file modificati di un repository del progetto, come testo | `repository` (vuoto = usa l'input dello step) |
| `save_note` | salva l'input dello step come nota del progetto (tab Dati → Note) | `title` (`{date}` e `{time}` diventano data e ora; stesso nome = nota sovrascritta) |

```
src/function/
  registry.py         FUNCTION_REGISTRY (tutte le funzioni, per nome) e get_function()
  spec.py             FunctionSpec: nome, descrizione, Params, run
  context.py          FunctionContext: progetto, input della run, service
  list/
    git_status.py
    save_note.py
```

## Come funziona

Uno step `FUNCTION` di un'automation ha `function_name` e `params`. Quando il worker arriva a quello step, `PipelineRunner`:

1. prende la funzione con `get_function(nome)`: `ValidationError` se non esiste (più) nel codice;
2. valida i `params` con il modello `Params` della funzione;
3. chiama `run(context, step_input, params)`: il testo restituito è l'output dello step e diventa l'input del successivo.

- **Parametri** (`Params`, pydantic): ogni campo ha un default e una `description`. Vengono validati **al salvataggio** dell'automation e **prima di ogni esecuzione**. L'editor degli step nella UI costruisce il form da qui (`GET /functions`): un campo `bool`, `int`, `float` o `str` diventa checkbox, numero o testo.
- **Errori**: un `AppError` sollevato dalla funzione fa fallire lo step con quel messaggio; qualsiasi altra eccezione lo fa fallire con «errore imprevisto: …».

## `FunctionContext`

Creato dal runner per ogni step funzione:

- `project_name`: il progetto dell'automation; le funzioni lavorano solo su quello;
- `pipeline_input`: l'input della run (l'input dello step arriva a parte, come argomento di `run`);
- i service: `git` (`GitService`), `project_data` (`ProjectDataService`).

## Aggiungere una funzione

```python
# function/list/<nome>.py
from pydantic import BaseModel, Field

from function.context import FunctionContext
from function.spec import FunctionSpec


class Params(BaseModel):
    campo: str = Field("", description="Mostrato nell'editor degli step.")


def run(context: FunctionContext, step_input: str, params: Params) -> str:
    ...
    return "output dello step"


NOME = FunctionSpec(name="nome", description="Descrizione nell'editor.", params=Params, run=run)
```

Poi la spec in `FUNCTION_REGISTRY` (`registry.py`). Per una funzione senza parametri: `params=NoParams`. Se serve un service nuovo, va aggiunto a `FunctionContext` e passato da `PipelineRunner`.

## Test

`test/unit/service/test_function_steps.py`: ogni funzione ha descrizione e default per tutti i parametri, parametri sbagliati che nominano il campo, step non validi rifiutati al salvataggio, esecuzione dal runner (`git_status` su un repository vero che passa l'output a un agente, `save_note`), errori attesi e imprevisti.
