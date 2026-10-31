# `src/core`

Le fondamenta del backend: errori, logging, cifratura, e i due punti dove tutto viene montato (app FastAPI e Container). `error.py`, `observability.py` e `secret_box.py` non dipendono da nessun altro modulo di `src/`.

```
src/core/
  error.py            AppError e sottoclassi: gli errori attesi
  observability.py    logging, LogPrefix, decoratore @observed
  secret_box.py       cifratura dei segreti salvati nel DB
  app.py              create_app(): l'API FastAPI, con errori → status HTTP e i router
  server.py           create_server(): l'API montata sotto /api e il frontend compilato (web/dist) altrove
  container.py        Container: crea tutti i service una volta per processo
src/
  api.py              entry dell'API: app = create_server(Config.get().web_dist)
  worker.py           entry del worker: automation, esecuzioni e chat di Copilot su tre corsie
```

## Avvio: API e worker

Due processi separati: l'API la avviano `run-app.py` e `run-web.py` (`resource/scripts/api_process.py`), il worker lo avvia l'API (`ProcessService`) o un terminale:

| Processo | Entry | Comando |
|---|---|---|
| API | `src/api.py` | `uvicorn api:app --app-dir src` (default, cambiabili con `API_APP`, `API_APP_DIR`, che non stanno nel `.env.example`). Con `API_RELOAD=true` gli script la avviano con `resource/scripts/api_reloader.py`, che la riavvia quando cambia un file Python in `src/`. `api:app` è il server di `core/server.py`: l'API (`core/app.py`) sotto `/api` e il frontend compilato (`web/dist`) nelle altre pagine |
| Worker | `src/worker.py` | `python src/worker.py` (default, cambiabile con `WORKER_SCRIPT`) |

Ognuno costruisce il suo `Container`.

Il worker ha **tre corsie indipendenti**, così nessuna aspetta le altre: le **automation** una alla volta (il thread principale), le **esecuzioni di Copilot** ognuna nel suo thread, in parallelo (la coda dà solo esecuzioni i cui repository sono liberi), i **turni di chat di Copilot** ognuno nel suo thread (la modalità piano legge e basta: non aspettano niente). Un'esecuzione di Copilot lunga non ferma le automation, né la chat. L'heartbeat dice la run in corso (`busy_run_id`) e le sessioni di Copilot in lavorazione (`busy_copilot_session_ids`).

**Lavori di un worker morto**: ogni claim salva chi ha preso il lavoro (`claimed_by` = `<host>-<pid>`, su `pipeline_run` e `copilot_session`). All'avvio e poi ogni 30 secondi ogni worker legge da Redis i worker che mandano l'heartbeat (scade dopo 10 secondi; lui conta sempre come vivo) e segna come interrotti i lavori `running` degli altri (`fail_orphaned`): run ed esecuzioni fallite, turni di chat chiusi con l'errore. Così più worker possono girare insieme senza chiudersi i lavori a vicenda, e un worker morto non lascia lavori bloccati anche se nessuno lo riavvia. Se Redis non risponde il controllo salta il giro: non si rischia di chiudere il lavoro di un worker vivo. I lavori presi prima di `claimed_by` (colonna vuota) contano come orfani: dopo l'aggiornamento riavvia anche i worker avviati da terminale.

## Container (`container.py`)

L'unico posto che crea i service e li collega: ognuno riceve nel costruttore quelli che usa. Nient'altro crea service.

- **All'avvio**: si connette a Postgres e Redis (`StoreService`), prepara lo schema e inserisce quello che manca: prima i modelli del catalogo, poi il catalogo dei tool, poi gli agenti globali di `definition/global-agent.yml` (`DefinitionService.seed_global_agents`). Quello che è stato modificato da UI non viene mai sovrascritto; un file rotto viene segnalato nel log, l'app parte lo stesso.
- **Nei test**: `Container(store_service=...)` con gli store in memoria.
- `DATAPIZZA_TRACE_SUMMARY=true` stampa in console il riepilogo di datapizza dopo ogni run.

## App FastAPI (`app.py`)

`create_app(container=None)`: costruisce il Container all'avvio (o usa quello passato dai test), registra la traduzione degli errori e include i [router](../controller/README.md).

## Errori (`error.py`)

Gli errori **attesi**: input sbagliato, risorsa mancante, servizio esterno giù. I service li sollevano con un messaggio già leggibile dall'utente (in italiano); tutto il resto è un bug.

| Errore | Quando | Status HTTP (`app.py`) |
|---|---|---|
| `NotFoundError` | la risorsa non esiste | 404 |
| `ValidationError` | input non valido | 400 |
| `ConflictError` | in conflitto con lo stato attuale (es. nome duplicato) | 409 |
| `UpstreamError` | è fallita una dipendenza (LLM, Atlassian, git, rete) | 502 |
| `AppError` | base di tutti (sollevata direttamente) | 500 |

```python
from core.error import NotFoundError

project = self._store.get_project(name)
if project is None:
    raise NotFoundError(f"Progetto non trovato: {name}")
```

Non confonderlo con il `ValidationError` di pydantic: nei moduli che usano entrambi si importa `from pydantic import ValidationError as PydanticValidationError`.

## Observability (`observability.py`)

- **`configure_logging(level)`**: un solo handler sulla console, formato `[LIVELLO] messaggio`. Si chiama all'avvio (API, worker) con `APP_LOG_LEVEL`; chiamarla più volte non duplica i log.
- **`log_info / log_warning / log_error / log_exception(prefix, message, *args)`**: log con il prefisso del componente, es. `[INFO] [WORKER] Fermato`. `log_exception` aggiunge il traceback.
- **`LogPrefix`**: l'elenco dei componenti che compaiono nei log. Un componente nuovo → una voce qui.
- **`@observed(prefix)`**: sui metodi dei service. Logga inizio, esito e durata; un `AppError` a INFO senza traceback (è previsto), qualsiasi altra eccezione a ERROR con traceback. Rilancia sempre.

```python
@observed(LogPrefix.GIT_SERVICE)
def log(self, project_name: str, ...) -> list[GitCommit]:
    ...
```

```
[INFO] [GIT_SERVICE] GitService.log started
[INFO] [GIT_SERVICE] GitService.log ok (42.3 ms)
[INFO] [GIT_SERVICE] GitService.log failed: Commit non trovato: abc1
```

## Segreti nel DB (`secret_box.py`)

`SecretBox(key)` cifra e decifra con Fernet (simmetrico) i segreti che l'app salva nel DB, per esempio i token Atlassian. La chiave è `MBARE_PILOT_SECRET_KEY` (vedi [`config`](../config.md)).

- **Senza chiave** l'app parte lo stesso: fallisce solo il salvataggio o la lettura di un segreto, con un `ValidationError` che spiega cosa impostare.
- **`decrypt`** restituisce `None` se il valore non è stato cifrato con questa chiave (chiave cambiata): il segreto va reinserito.
- **Generare la chiave**:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Cambiare la chiave rende illeggibili i segreti già salvati.

## Test

`test/unit/core/test_secret_box.py`: cifratura, chiave mancante o non valida. `test/unit/core/test_container.py`: riepilogo di datapizza acceso o spento dalla config, `Config.get()`/`set()`.
