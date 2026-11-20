# Mbare Pilot

**Il lavoro di tutti i giorni in un flusso solo.** Mbare Pilot mette insieme Jira, Confluence, i repository e GitHub Copilot: da un'attività un agente pianifica i task, Copilot sviluppa e scrive le bozze, Dev esegue le procedure, e tu decidi nei punti di controllo. I nomi del cliente escono solo mascherati e ogni chiamata ha il suo costo in chiaro.

**[Presentazione e documentazione → pittalavito.github.io/mbare-pilot-app](https://pittalavito.github.io/mbare-pilot-app/)**

## Cosa fa

- **Attività**: nascono dai riferimenti (issue Jira, pagine Confluence, codice, contesto) e da quello che vuoi fare.
- **Pianificatore**: scompone l'attività in task (sviluppo, analisi, Confluence, Jira), ogni sviluppo con il suo pre e il suo post.
- **Il giro**: delega a Copilot, lo segue e si ferma dove servi tu: l'ok al piano, la conferma, «📤 Pubblica».
- **Agenti**: Segretario, Refiner, Pianificatore, Dev, Architetto, Copilot e piccoli agenti con risposta strutturata. Il contesto (generale e del progetto) sta in un RAG con pgvector.
- **Osservabilità**: run, token, costi, tracce e «🔍 Cosa ha visto il modello», mascherato o in chiaro.
- **Masking**: repository, persone, email e termini del cliente diventano alias prima di ogni chiamata.
- **Automation**: grafi di step senza LLM dove serve. Il motore è pronto, ma oggi non entra nel flusso.

## Avvio rapido

Prerequisiti: Python 3.12, [uv](https://docs.astral.sh/uv/), Docker, Node.js ≥ 22.13.

1. Copia `.env.example` in `.env` e genera `MBARE_PILOT_SECRET_KEY`: il comando è nel file.
2. Installa le dipendenze:

```bash
python resource/scripts/start-venv.py
```

3. Avvia Postgres e Redis:

```bash
python resource/scripts/start-docker.py
```

4. Avvia l'app. Compila il frontend se serve e serve tutto su `API_URL`; il worker si accende dall'intestazione della pagina.

```bash
python resource/scripts/run-app.py
```

**Senza terminali**: installa una volta il launcher. Parte da solo a ogni accesso al PC (in background, senza finestre) e serve una pagina su `LAUNCHER_URL` (default http://127.0.0.1:8090) da salvare nei preferiti del browser. Da lì «Avvia» fa i passi 3 e 4 (accende anche Docker Desktop se è spento) e apre l'app; «Ferma» ferma API e worker, «Ferma anche Docker» anche i container. Log in `resource/logs/launcher.log`; `--remove` toglie l'avvio automatico.

```bash
python resource/scripts/install-launcher.py
```

Per sviluppare il frontend con la ricarica a caldo (API e Vite su `WEB_PORT`, [web/README.md](web/README.md)):

```bash
python resource/scripts/run-web.py
```

Le definizioni di default (agenti, chatbot, prompt di Copilot, contesto generale) sono in [resource/definition](resource/definition/README.md): non c'è niente da copiare. Quello che cambi va in `<MBARE_PILOT_HOME>/definition/` e vince su quello dell'app. La cartella dei dati (`MBARE_PILOT_HOME`) sta **fuori dal repo**.

Se lo schema del DB cambia l'app non parte finché non lo ricrei (non ci sono migrazioni):

```bash
docker compose --env-file .env -f resource/docker/docker-compose.yml down -v
```

## Struttura

```
src/                  backend Python: due processi
  api.py, worker.py   API (FastAPI, serve anche il frontend) e worker (giro, Copilot, automation)
  core/               app, container, errori, logging, cifratura
  controller/         endpoint HTTP e server MCP
  service/            regole dell'app
  domain/             LLM, agenti, git, Atlassian, Copilot, store
  tool/               tool degli agenti e delle automation (un solo registro)
  models/             modelli domain, store, controller
web/                  frontend React + Vite + Mantine (client tipizzato dall'OpenAPI)
test/                 pytest
resource/
  definition/         agenti, chatbot, prompt, contesto generale, ricerche salvate
  scripts/            avvio (anche il launcher nel browser), test, export del DB, valutazioni
  eval/               set di prova delle valutazioni
  plans/              i piani di lavoro
docs/                 sito GitHub Pages e documentazione per package (docs/doc)
```

Il codice va in un solo verso: `frontend → /api → controller → service → domain → store`. Dati: **Postgres** con pgvector per quello che l'app definisce e registra, **Redis** per tracce e heartbeat, **file** su disco per note, task, attività e definizioni.

## Sviluppo

Ogni blocco di lavoro ha un piano in [resource/plans](resource/plans/README.md) e la sua PR. La CI (`.github/workflows/ci.yml`) chiede:

```bash
python resource/scripts/run-test.py
```

```bash
uv run ruff check .
```

```bash
uv run mypy
```

```bash
cd web && npm test && npx tsc -b
```

Il coverage di `src/` deve restare ≥ 95% (`fail_under` in `pyproject.toml`): la soglia si alza quando il coverage cresce, non si abbassa per far passare la CI.

Altri comandi:

- export del DB in `../mbare-pilot-back-up/db/` (anche da **Admin → Backup**):

```bash
python resource/scripts/export-db.py
```

- valutazioni con i modelli veri sui set di `resource/eval/` (anche da **Admin → Observability → Metriche**):

```bash
python resource/scripts/eval-wip.py --model openrouter/google/gemini-3.1-flash-lite
```

```bash
python resource/scripts/eval-rag.py --embedder hashing --embedder openrouter/openai/text-embedding-3-small
```

### Tool nuovi con Claude Code

Quando a un'automation manca un tool, l'Architetto scrive una richiesta in **Admin → Richieste di tool**. Per lavorarla:

1. «Genera il token» e lancia il comando `claude mcp add …` nella cartella del clone.
2. In Claude Code chiedi «lavora le richieste di tool»: scrive il tool con i test e apre la PR.
3. Dopo il merge e il riavvio dell'app il tool è nel catalogo.

## Documentazione

La documentazione per package sta in [docs/doc](docs/doc/README.md), con la stessa struttura del codice, ed è navigabile anche dal [sito](https://pittalavito.github.io/mbare-pilot-app/#doc/README.md). Il frontend ha la sua in [web/README.md](web/README.md).
