# `src/domain/store/db`

Lo store su Postgres: tutto quello che l'app definisce e registra (progetti, agenti, chatbot, automation, run, catalogo dei modelli). Un repository per tabella o gruppo di tabelle, più, per ogni aggregato, il mapper da e verso i modelli di dominio.

```
src/domain/store/db/
  repository.py               Engine (connessione + schema), SqlRepository (base), transaction (unit of work)
  project_repository.py       progetti
  atlassian_repository.py     sito Atlassian di un progetto (token cifrato)
  atlassian_favorite_repository.py  issue e pagine preferite di un progetto
  role_repository.py          ruoli degli agenti
  prompt_repository.py        versioni dei system prompt
  agent_config_repository.py  agenti (Libreria e di progetto)
  tool_repository.py          catalogo dei tool
  chat_model_repository.py    catalogo dei modelli LLM
  chatbot_repository.py       chatbot, conversazioni, messaggi, cache (automation_cache)
  pipeline_repository.py      automation, step, collegamenti del grafo, run (anche coda del worker), step delle run
  run_repository.py           run degli agenti e loro tool call
  mapper.py                   condiviso dai mapper: as_utc, saved_id
  run_mapper.py               Adapter/Factory delle run
  catalog_mapper.py           …dei modelli e dei tool
  agent_mapper.py             …di ruoli, prompt e agenti
  project_mapper.py           …dei progetti
  chatbot_mapper.py           …di chatbot, conversazioni, messaggi, cache
  pipeline_mapper.py          …di automation e run
  atlassian_mapper.py         …di sito e preferiti Atlassian
  copilot_mapper.py           …di sessioni, messaggi e turni di Copilot
```

Le tabelle stanno in [`models/store/db.py`](../../../models/README.md), con la mappa dello schema in testa. Chi usa questi repository e mapper sono gli [store per aggregato](../../../service/README.md#gli-store-servicestore) (`service/store/`): fuori da uno store circolano solo modelli di dominio, mai righe.

## Engine e schema (`repository.py`)

`Engine.create_db_engine(DATABASE_URL)` si connette e prepara lo schema all'avvio:

1. su Postgres attiva l'estensione **pgvector** (`CREATE EXTENSION IF NOT EXISTS vector`);
1. rinomina le **tabelle rinominate nel codice** (`RENAMED_TABLES` in `repository.py`, es. `chat_route` → `automation_cache`) con `ALTER TABLE … RENAME TO`, se c'è ancora solo quella vecchia: le righe restano; indici e sequenze tengono il vecchio nome, senza conseguenze;
2. aggiunge alle tabelle esistenti le **colonne nuove** che si possono aggiungere senza toccare le righe: nullable, o con un default scalare (es. `model: str = ""`), che diventa il `DEFAULT` della colonna (`ALTER TABLE … ADD COLUMN`, nel log);
3. controlla le tabelle esistenti: se le colonne nel codice sono ancora diverse (una tolta, rinominata, nuova obbligatoria senza default), la tabella va ricreata;
4. `create_all` crea le tabelle che mancano.

**Niente migrazioni** (niente Alembic). A parte l'aggiunta di colonne del punto 2, una tabella cambiata nel codice viene ricreata, insieme alle tabelle che la referenziano, **solo se sono tutte vuote**. Se ha dati l'app non parte e dice quale tabella migrare o svuotare a mano: così non si perde mai niente in silenzio. Il tipo di una colonna esistente non viene confrontato.

## Base dei repository (`SqlRepository`)

Una sessione per operazione e il CRUD per chiave primaria; i repository concreti aggiungono le loro query.

| Metodo | Cosa fa |
|---|---|
| `get(pk)` | la riga, `None` se non c'è |
| `list()` | tutte le righe |
| `save(row)` | inserisce o aggiorna, restituisce la riga salvata |
| `insert_missing(rows)` | inserisce solo le righe la cui chiave non c'è ancora: è il **seed** dei default (modelli, tool), che non sovrascrive mai le modifiche fatte da UI |
| `delete(pk)` | `True` se ha cancellato una riga |
| `_grouped(statement, ids, key)` | per i repository concreti: le righe figlie di molti genitori con **una query** (`IN (...)`), raggruppate per id del genitore; ogni id c'è, anche senza righe. Evita una query per genitore (N+1) |

## Transazioni (`transaction`)

Ogni operazione di un repository ha la sua sessione e il suo commit. Quando più scritture devono riuscire o fallire **insieme**, si aprono dentro `transaction(engine)`:

```python
with transaction(self._engine):
    row = self._pipelines.save(...)
    self._steps.replace(saved_id(row), ...)
    self._edges.replace(saved_id(row), ...)
```

Dentro il blocco tutti i repository usano la stessa sessione: il loro `commit` diventa un `flush` (gli id generati ci sono già), il commit vero è uno solo alla fine; se il blocco solleva, rollback di tutto. Un blocco aperto dentro un altro si unisce a quello esterno. Le righe restituite restano leggibili dopo il commit. Oggi lo usa `PipelineStore.save_pipeline` (automation, step e collegamenti): per questo `PipelineStore` riceve l'engine.

## Query notevoli

| Dove | Cosa |
|---|---|
| `DbPipelineRunRepository.claim_next()` | prende la run `queued` più vecchia e la passa a `running` in modo atomico con `FOR UPDATE SKIP LOCKED`: due worker non prendono mai la stessa run |
| `DbPipelineStepRepository.replace()` | salva gli step di un'automation in una transazione: aggiorna quelli con id, inserisce i nuovi, cancella quelli tolti |
| `DbPromptRepository.create_version()` | aggiunge la versione `max + 1` del prompt di un ruolo; le versioni non si modificano mai |
| `DbChatModelRepository.keys_in_use()` | i modelli usati da agenti, chatbot e step: questi non si possono eliminare dal catalogo |
| `DbRunRepository.save_rows()` | salva una run e le sue tool call insieme |

## Conversioni (`<aggregato>_mapper.py`)

Ogni aggregato ha il suo modulo, accanto ai suoi repository, con due classi di metodi statici:

- **`Adapter`** (riga → dominio): `to_project`, `to_agent_config`, `to_pipeline` (con i suoi step), `to_run_summary`, …
- **`Factory`** (dominio → riga): `to_project_row`, `to_pipeline_step_row`, `to_run_row`, `to_tool_rows`, …

`mapper.py` ha quello che servono a tutti: `as_utc` (SQLite restituisce le date senza fuso: sono UTC) e `saved_id` (l'id di una riga letta o appena salvata; le tabelle lo dichiarano `int | None` perché una riga nuova non ce l'ha).

Il token Atlassian entra e esce già cifrato: la cifratura con [`SecretBox`](../../../core/README.md) la fa `AtlassianStore`.

## Cose da sapere

- **Cancellazione a cascata**: rimuovere un progetto cancella dal DB quello che gli appartiene (agenti, chatbot con le conversazioni, automation con le loro esecuzioni, sito e preferiti Atlassian). Restano le run degli agenti (`agent_run`, `tool_call`: lo storico di Observability, senza chiave esterna verso il progetto), l'uso dei turni di Copilot (`copilot_turn`, senza chiave esterna nemmeno verso la sessione) e le cartelle sul disco.
- **RAG non ancora implementato**: le tabelle `document` e `chunk` (con l'embedding pgvector) esistono, ma non hanno repository né codice che le usi.

## Aggiungere una tabella

1. La classe `*Table` in `models/store/db.py`.
2. Un `<nome>_repository.py` che estende `SqlRepository`.
3. `Adapter.to_<x>` e `Factory.to_<x>_row` nel mapper del suo aggregato (`<aggregato>_mapper.py`), o in un mapper nuovo se è un aggregato nuovo.
4. I metodi nello store dell'aggregato (`service/store/<aggregato>_store.py`), che crea il repository nel suo `__init__`. Per un aggregato nuovo: lo store, il suo attributo in `Stores`, la fixture in `test/conftest.py` e il Container che lo passa ai service che lo usano.

## Test

- `test/unit/domain/store/db/test_run_repository.py`: salvataggio di una run con le tool call, elenco dalla più recente, cancellazione.
- `test/unit/domain/store/db/test_schema_refresh.py`: colonna nuova con default aggiunta tenendo le righe, tabella cambiata e vuota ricreata con chi la referenzia, tabella cambiata con dati che blocca l'avvio, schema aggiornato lasciato com'è.
- `test/unit/service/store/test_pipeline_store.py`: `save_pipeline` tutto o niente, transazioni annidate, numero di query di `list_pipelines` e `list_pipeline_runs`.
- `test/unit/service/store/test_run_store.py`: fatti, tool call e trace di una run, date in UTC.

Girano su SQLite in memoria, con la fixture `engine` di `test/conftest.py`. Gli altri repository sono coperti dai test dei service.
