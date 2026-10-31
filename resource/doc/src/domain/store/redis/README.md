# `src/domain/store/redis`

Lo store su Redis: dati che non servono in SQL perché sono grandi e si leggono uno alla volta (i trace delle run), perché valgono solo pochi secondi (l'heartbeat dei worker) o perché sono mappe da leggere a ogni run (il mascheramento).

```
src/domain/store/redis/
  repository.py          keyspace, Client (connessione), RedisRepository (base)
  trace_repository.py    RedisTraceRepository: trace verbatim delle run
  worker_repository.py   RedisWorkerRepository: heartbeat dei worker
  mask_repository.py     RedisMaskRepository: mappe di mascheramento dei progetti
  trace_mapper.py        Factory dei trace
  worker_mapper.py       Factory/Adapter degli heartbeat
  mask_mapper.py         Adapter delle mappe di mascheramento
```

Chi lo usa sono gli [store](../../../service/README.md#gli-store-servicestore) `RunStore` (trace), `WorkerStore` e `MaskStore`. I record salvati (`AgentTraceRecord`, `WorkerHeartbeatRecord`) stanno in [`models/store/redis.py`](../../../models/README.md), come JSON.

## Keyspace

Tutte le chiavi hanno la forma `app:<keyspace>:<suffisso>`. I keyspace sono definiti in un unico posto, `repository.py`: è lo "schema" di Redis.

| Keyspace | Suffisso | Valore | Scadenza | Usato da |
|---|---|---|---|---|
| `agent-trace` | `run_id` | `AgentTraceRecord`: input, output, tool call, chiamate LLM | nessuna | Admin → Observability, dettaglio di una run |
| `worker` | `<host>-<pid>` | `WorkerHeartbeatRecord`: pid, avvio, ultimo segnale, run in corso | 10 s | `GET /workers`, tab Automation, pannello Backend |
| `mask` | `<progetto>:entries`, `<progetto>:index`, `<progetto>:counter:<categoria>` | hash alias → `MaskRecord`; hash valore (minuscolo) → alias; contatore per categoria | nessuna | `MaskingService`: ogni run di un progetto, Impostazioni → Mascheramento |

Divisione con Postgres: i **fatti** di una run (esito, token, costi, tool usati) stanno in SQL (`agent_run`, `tool_call`), per elencarli e filtrarli; il **trace verbatim** sta qui, con lo stesso `run_id`.

## Base (`repository.py`)

- **`RedisKeyspace(name, value, default_ttl_seconds)`**: un keyspace; `default_ttl_seconds <= 0` = chiavi permanenti.
- **`Client.create_redis_client(url)`**: si connette e fa un `ping`. Redis è obbligatorio: se non risponde l'app non parte (`RuntimeError`), niente funzionamento a metà.
- **`RedisRepository`**: la base dei repository. `_set` applica la scadenza del keyspace, `_load` legge e valida il JSON; un valore illeggibile viene scartato con un warning (`REDIS_MALFORMED_DATA`) e trattato come assente.

## Repository

| Repository | Metodi |
|---|---|
| `RedisTraceRepository` | `save(record)`, `load(run_id)`, `delete(run_id)` |
| `RedisWorkerRepository` | `save(record)` (rinnova la scadenza), `list_alive()` (i worker con la chiave ancora valida), `delete(worker_id)` |
| `RedisMaskRepository` | `list(progetto)`, `find(progetto, valore)`, `add(...)` (alias esistente o nuovo, con il contatore della categoria), `delete(progetto, alias)`, `delete_project(progetto)` |

## Conversioni (`<x>_mapper.py`)

Un mapper per uso, accanto al suo repository:

- **`Factory`** (dominio → record): `trace_mapper.to_trace_record(AgentRunRecord)`, `worker_mapper.to_heartbeat_record(WorkerStatus)`.
- **`Adapter`** (record → dominio): `worker_mapper.to_worker_status(record)`, `mask_mapper.to_mask_entry(record)` (i record delle maschere li scrive il repository, che assegna l'alias).

Il trace letto torna come `AgentTraceRecord`: l'API lo restituisce così com'è.

## Aggiungere un uso di Redis

1. Un `RedisKeyspace` in `repository.py` (nome, cosa contiene, scadenza).
2. Il record in `models/store/redis.py`.
3. Un repository `<nome>_repository.py` che estende `RedisRepository`, con Factory/Adapter in `<nome>_mapper.py` se il record è diverso dal modello di dominio.
4. I metodi nello store dell'aggregato (`service/store/`), o uno store nuovo con il suo attributo in `Stores` e la fixture in `test/conftest.py`.

## Test

`test/unit/domain/store/redis/test_trace_repository.py`: salvataggio e lettura, trace mancante, valore illeggibile. Usano fakeredis tramite la fixture `redis_client` di `test/conftest.py`. L'heartbeat dei worker è coperto dai test di `PipelineService`, `RunStore` da `test/unit/service/store/test_run_store.py`.
