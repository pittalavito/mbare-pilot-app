# `src/core`

Le fondamenta del backend. `error.py`, `observability.py` e `secret_box.py` non dipendono da nessun altro modulo di `src/`.

```
src/core/
  error.py            AppError e sottoclassi: gli errori attesi
  observability.py    logging, LogPrefix, decoratore @observed
  secret_box.py       cifratura dei segreti salvati nel DB
  app.py              create_app(): l'API FastAPI, errori → status HTTP, router, server MCP
  server.py           l'API sotto /api e il frontend compilato (web/dist) altrove
  container.py        Container: crea tutti i service una volta per processo
src/
  api.py              entry dell'API (uvicorn api:app --app-dir src)
  worker.py           entry del worker: run delle automation, esecuzioni di Copilot, giro delle attività, pre e post, valutazioni
```

## Processi

- **API**: la avviano `run-app.py`, `run-web.py` o il launcher. Con `API_RELOAD=true` si riavvia quando cambia il codice.
- **Worker**: lo avvia e lo ferma l'API (`ProcessService`), oppure un terminale (`python src/worker.py`). Scrive un heartbeat in Redis.

Ognuno costruisce il suo `Container`: l'unico posto che crea i service e li collega. All'avvio si connette a Postgres e Redis, prepara lo schema e inserisce quello che manca (modelli, catalogo dei tool), poi allinea le definizioni dai file. Nei test si passa `Container(stores=...)`.

## Errori (`error.py`)

Gli errori attesi, con un messaggio già leggibile (in italiano); tutto il resto è un bug.

| Errore | Quando | Status HTTP |
|---|---|---|
| `NotFoundError` | la risorsa non esiste | 404 |
| `ValidationError` | input non valido | 400 |
| `ConflictError` | in conflitto con lo stato attuale | 409 |
| `UpstreamError` | è fallita una dipendenza (LLM, Atlassian, git, rete) | 502 |
| `AppError` | la base | 500 |

Da non confondere con il `ValidationError` di pydantic: dove servono entrambi, `from pydantic import ValidationError as PydanticValidationError`.

## Log (`observability.py`)

- `configure_logging(level)` all'avvio, con `APP_LOG_LEVEL`; formato `[LIVELLO] [COMPONENTE] messaggio`.
- `log_info`, `log_warning`, `log_error`, `log_exception(prefix, ...)`; `LogPrefix` è l'elenco dei componenti.
- `@observed(prefix)` sui metodi dei service: inizio, esito e durata; un `AppError` a INFO, ogni altra eccezione a ERROR con traceback. Rilancia sempre.

## Segreti (`secret_box.py`)

`SecretBox(key)` cifra con Fernet i segreti salvati nel DB (es. i token Atlassian), con la chiave `MBARE_PILOT_SECRET_KEY`. Senza chiave l'app parte, ma salvare o leggere un segreto è un errore che spiega cosa impostare. Cambiare la chiave rende illeggibili i segreti già salvati.

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
