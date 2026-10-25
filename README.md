# Mbare Pilot

App agentica per lavorare su **progetti** (cartelle del PC).

## Avvio rapido

Prerequisiti: Python 3.12, [uv](https://docs.astral.sh/uv/), Docker, Node.js ≥ 22.13.

1. Copia `.env.example` in `.env` e genera `MBARE_PILOT_SECRET_KEY` (il comando è nel file): cifra i segreti salvati nel DB.
2. Installa le dipendenze:

```bash
python resource/scripts/start-venv.py
```

3. Avvia Postgres e Redis:

```bash
python resource/scripts/start-docker.py
```

4. Avvia l'app: compila il frontend se serve e avvia l'API, che serve tutto su `API_URL`. Il worker si accende dall'intestazione della pagina.

```bash
python resource/scripts/run-app.py
```

   Per sviluppare il frontend, con la ricarica a caldo: API e Vite su `WEB_PORT` ([web/README.md](web/README.md)).

```bash
python resource/scripts/run-web.py
```

Test con coverage (il frontend ha i suoi: `npm test` in `web/`):

```bash
python resource/scripts/run-test.py
```

Export del DB in `../mbare-pilot-back-up/db/` (anche da **Admin → Backup**):

```bash
python resource/scripts/export-db.py
```

## Frontend

React + Vite + Mantine in `web/` ([web/README.md](web/README.md)): parla **solo** con l'API, sotto `/api`.

- **Progetti**: Chat, Automation, Dati, Git, Atlassian, Impostazioni (Atlassian, mascheramento, definizioni, agenti del progetto)
- **Libreria**: agenti, ruoli, prompt versionati, tool globali
- **Admin**: Servizi, Observability, Modelli, Backup

Nell'intestazione: lo stato dell'API, il **worker** (avvia/ferma, lo gestisce l'API) e i log di API e worker.

## Backend

Backend in `src/`: due processi.

- **API** (`src/api.py`): su `API_URL` serve l'API sotto `/api` (documentazione interattiva su `/api/docs`) e il frontend compilato (`web/dist`) in tutte le altre pagine. La avviano `run-app.py` e `run-web.py`.
- **Worker** (`src/worker.py`): esegue le automation messe in coda, una alla volta. Lo avvia e lo ferma l'API (PID in `resource/run/`, log in `resource/logs/`).

Dati: **Postgres** (con pgvector) per tutto quello che l'app definisce e registra, **Redis** per i trace delle run e l'heartbeat dei worker, **file** su disco nella cartella dei dati (`MBARE_PILOT_HOME`): note, file e definizioni YAML dei progetti. Dashboard: Adminer su `POSTGRES_DASHBOARD_PORT`, Redis Commander su `REDIS_DASHBOARD_PORT` (link anche in **Admin → Servizi**).

```
src/
  api.py, worker.py   entry dei due processi
  config.py           impostazioni da .env
  core/               errori, logging, cifratura, app FastAPI e server (API + frontend), Container
  controller/         endpoint HTTP
  service/            regole dell'app e motore delle automation
  domain/             client LLM, agenti, git, Atlassian, store
  tool/, function/    tool degli agenti, funzioni degli step
  models/             modelli: domain, store, controller (separati)
web/                  frontend React (client tipizzato generato dall'OpenAPI dell'API)
```

Flusso: `frontend → HTTP /api → controller → service → domain → store`.

## Documentazione

Indice in [resource/doc](resource/doc/README.md): un file per package, con la stessa struttura del progetto.
