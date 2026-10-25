# Mbare Pilot

App agentica per lavorare su **progetti** (cartelle del PC).

## Avvio rapido

Prerequisiti: Python 3.12, [uv](https://docs.astral.sh/uv/), Docker.

1. Copia `.env.example` in `.env` e genera `MBARE_PILOT_SECRET_KEY` (il comando è nel file): cifra i segreti salvati nel DB.
2. Installa le dipendenze:

```bash
python resource/scripts/start-venv.py
```

3. Avvia Postgres e Redis:

```bash
python resource/scripts/start-docker.py
```

4. Avvia la UI, e da lì il backend (pannello **Backend** nella barra laterale):

```bash
python resource/scripts/run-ui.py
```

   Oppure il frontend React nuovo (in migrazione, richiede Node.js ≥ 22.13): avvia API e frontend insieme, il worker si avvia dall'intestazione della pagina ([web/README.md](web/README.md)):

```bash
python resource/scripts/run-web.py
```

Test con coverage:

```bash
python resource/scripts/run-test.py
```

Export del DB in `../mbare-pilot-back-up/db/` (anche da **Admin → Backup**):

```bash
python resource/scripts/export-db.py
```

## UI

Frontend in `ui/`: parla **solo** con l'API del backend (`API_URL`), parte su `UI_PORT`.

- **Progetti**: Chat, Automation, Dati, Git, Impostazioni (Atlassian, agenti del progetto)
- **Libreria**: agenti, ruoli, prompt versionati, tool globali
- **Admin**: Servizi, Observability, Modelli, Backup

API e worker si accendono e spengono dal pannello **Backend** nella barra laterale (stato, ▶/⏹, log). Restano attivi anche se ricarichi o riavvii la UI (PID in `resource/run/`, log in `resource/logs/`).

## Backend

Backend in `src/`: due processi, entrambi avviati dal pannello Backend della UI.

- **API** (`src/api.py`): l'API HTTP che usa la UI, su `API_URL`. Documentazione interattiva su `/docs`.
- **Worker** (`src/worker.py`): esegue le automation messe in coda, una alla volta.

Dati: **Postgres** (con pgvector) per tutto quello che l'app definisce e registra, **Redis** per i trace delle run e l'heartbeat dei worker, **file** su disco per note e file dei progetti (`~/.mbare-pilot/projects/` di default). Dashboard: Adminer su `POSTGRES_DASHBOARD_PORT`, Redis Commander su `REDIS_DASHBOARD_PORT` (link anche in **Admin → Servizi**).

```
src/
  api.py, worker.py   entry dei due processi
  config.py           impostazioni da .env
  core/               errori, logging, cifratura, app FastAPI, Container
  controller/         endpoint HTTP
  service/            regole dell'app e motore delle automation
  domain/             client LLM, agenti, git, Atlassian, store
  tool/, function/    tool degli agenti, funzioni degli step
  models/             modelli: domain, store, controller (separati)
```

Flusso: `UI → HTTP → controller → service → domain → store`.

## Documentazione

Indice in [resource/doc](resource/doc/README.md): un file per package, con la stessa struttura del progetto.
