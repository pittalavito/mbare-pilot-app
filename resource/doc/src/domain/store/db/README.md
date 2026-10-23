# `src/domain/store/db`

Lo store su Postgres: tutto quello che l'app definisce e registra (progetti, agenti, chatbot, automation, run, catalogo dei modelli). Un repository per tabella o gruppo di tabelle, più le conversioni da e verso i modelli di dominio.

```
src/domain/store/db/
  repository.py               Engine (connessione + schema), SqlRepository (base)
  project_repository.py       progetti
  atlassian_repository.py     sito Atlassian di un progetto (token cifrato)
  role_repository.py          ruoli degli agenti
  prompt_repository.py        versioni dei system prompt
  agent_config_repository.py  agenti (Libreria e di progetto)
  tool_repository.py          catalogo dei tool
  chat_model_repository.py    catalogo dei modelli LLM
  chatbot_repository.py       chatbot, conversazioni, messaggi
  pipeline_repository.py      automation, step, run (anche coda del worker), step delle run
  run_repository.py           run degli agenti e loro tool call
  store.py                    punto unico di import + Adapter (lettura) e Factory (scrittura)
```

Le tabelle stanno in [`models/store/db.py`](../../../models/README.md), con la mappa dello schema in testa. Chi usa questi repository è `StoreService`: fuori dallo store circolano solo modelli di dominio, mai righe.

## Engine e schema (`repository.py`)

`Engine.create_db_engine(DATABASE_URL)` si connette e prepara lo schema all'avvio:

1. su Postgres attiva l'estensione **pgvector** (`CREATE EXTENSION IF NOT EXISTS vector`);
2. controlla le tabelle esistenti: se le colonne nel codice sono cambiate, la tabella va ricreata;
3. `create_all` crea le tabelle che mancano.

**Niente migrazioni** (niente Alembic). Una tabella cambiata nel codice viene ricreata, insieme alle tabelle che la referenziano, **solo se sono tutte vuote**. Se ha dati l'app non parte e dice quale tabella migrare o svuotare a mano: così non si perde mai niente in silenzio.

## Base dei repository (`SqlRepository`)

Una sessione per operazione e il CRUD per chiave primaria; i repository concreti aggiungono le loro query.

| Metodo | Cosa fa |
|---|---|
| `get(pk)` | la riga, `None` se non c'è |
| `list()` | tutte le righe |
| `save(row)` | inserisce o aggiorna, restituisce la riga salvata |
| `insert_missing(rows)` | inserisce solo le righe la cui chiave non c'è ancora: è il **seed** dei default (agenti, modelli, tool), che non sovrascrive mai le modifiche fatte da UI |
| `delete(pk)` | `True` se ha cancellato una riga |

## Query notevoli

| Dove | Cosa |
|---|---|
| `DbPipelineRunRepository.claim_next()` | prende la run `queued` più vecchia e la passa a `running` in modo atomico con `FOR UPDATE SKIP LOCKED`: due worker non prendono mai la stessa run |
| `DbPipelineStepRepository.replace()` | salva gli step di un'automation in una transazione: aggiorna quelli con id, inserisce i nuovi, cancella quelli tolti |
| `DbPromptRepository.create_version()` | aggiunge la versione `max + 1` del prompt di un ruolo; le versioni non si modificano mai |
| `DbChatModelRepository.keys_in_use()` | i modelli usati da agenti, chatbot e step: questi non si possono eliminare dal catalogo |
| `DbRunRepository.save_rows()` | salva una run e le sue tool call insieme |

## Conversioni (`store.py`)

- **`Adapter`** (riga → dominio): `to_project`, `to_agent_config`, `to_pipeline` (con i suoi step), `to_run_summary`, …
- **`Factory`** (dominio → riga): `to_project_row`, `to_pipeline_step_row`, `to_run_row`, `to_tool_rows`, …

Il token Atlassian entra e esce già cifrato: la cifratura con [`SecretBox`](../../../core/README.md) la fa `StoreService`.

## Cose da sapere

- **Cancellazione a cascata**: rimuovere un progetto cancella dal DB quello che gli appartiene (agenti, chatbot con le conversazioni, automation con le loro esecuzioni, sito Atlassian). Restano le run degli agenti (`agent_run`, `tool_call`: lo storico di Observability, senza chiave esterna verso il progetto) e le cartelle sul disco.
- **RAG non ancora implementato**: le tabelle `document` e `chunk` (con l'embedding pgvector) esistono, ma non hanno repository né codice che le usi.

## Aggiungere una tabella

1. La classe `*Table` in `models/store/db.py`.
2. Un `<nome>_repository.py` che estende `SqlRepository`, esportato da `store.py`.
3. `Adapter.to_<x>` e `Factory.to_<x>_row` in `store.py`.
4. I metodi in `StoreService` e il repository creato nel suo `__init__`.

## Test

- `test/unit/domain/store/db/test_run_repository.py`: salvataggio di una run con le tool call, elenco dalla più recente, cancellazione.
- `test/unit/domain/store/db/test_schema_refresh.py`: tabella cambiata e vuota ricreata con chi la referenzia, tabella cambiata con dati che blocca l'avvio, schema aggiornato lasciato com'è.

Girano su SQLite in memoria, con la fixture `engine` di `test/conftest.py`. Gli altri repository sono coperti dai test dei service.
