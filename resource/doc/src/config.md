# `src/config.py`

`Config`: le impostazioni del backend, da `.env`. Una sola istanza per processo.

Legge `.env` dalla root del progetto (pydantic-settings). Il nome della variabile è il campo in maiuscolo: `database_url` ← `DATABASE_URL`.

- **Un'istanza per processo**: leggila ovunque con `Config.get()`, senza passarla in giro. La prima chiamata carica il `.env`.
- **Nei test**: `Config.set(Config(_env_file=None, ...))` la sostituisce; `Config.set(None)` la fa ricaricare.
- **Obbligatori**: `DATABASE_URL`, `REDIS_URL`. Tutto il resto ha un default.
- **Segreti** (`SecretStr`): `MBARE_PILOT_SECRET_KEY`, `OPENROUTER_API_KEY`, `OPENAI_API_KEY`; non finiscono mai nei log o nelle risposte per errore.
- **`masked()`**: tutte le impostazioni pronte da mostrare (Admin → Servizi). Maschera i campi che contengono `password`, `api_key`, `secret`, `token` e le credenziali dentro gli URL (`postgresql://app:********@...`).

Valori derivati:

| Proprietà | Da | Default |
|---|---|---|
| `data_home` | `MBARE_PILOT_HOME` | `~/.mbare-pilot` |
| `worker_script` | `WORKER_SCRIPT` | `src/worker.py`: il worker che l'API avvia (`ProcessService`) |
| `copilot_command` | `COPILOT_COMMAND` | `copilot`: GitHub Copilot CLI (nome nel PATH o percorso) |
| `copilot_model` | `COPILOT_MODEL` | vuoto: il modello predefinito di Copilot |
| `copilot_github_token` | `COPILOT_GITHUB_TOKEN` | vuoto: vale il login fatto con `copilot` → `/login` |
| `copilot_planning_timeout_minutes`, `copilot_execution_timeout_minutes` | `COPILOT_PLANNING_TIMEOUT_MINUTES`, `COPILOT_EXECUTION_TIMEOUT_MINUTES` | 5 e 60: un turno di preparazione, un'esecuzione |
| `automation_cache_threshold` | `AUTOMATION_CACHE_THRESHOLD` (vecchio nome `CHAT_ROUTE_THRESHOLD`) | 0,9: quanto un messaggio deve somigliare (coseno) a una voce della cache delle automation per lanciarne l'automation senza agente |
| `automation_cache_embedder` | `AUTOMATION_CACHE_EMBEDDER` (vecchio nome `CHAT_ROUTE_EMBEDDER`) | `hashing`: l'embedder della cache (oppure `openrouter/<modello>`) |
| `app_root`, `run_dir`, `logs_dir` | cartella dell'app, `resource/run`, `resource/logs` | file PID e log di API e worker |
| `web_dist` | `web/dist` | il frontend compilato che l'API serve (`core/server.py`) |
| `project_data_root` | `data_home / "project"` | note, file caricati e contesto dei progetti (`project/<slug>/`) |
| `definitions_root` | `data_home / "definition"` | agenti, chatbot e automation come YAML (vedi [definitions](../definitions.md)) |
| `project_root_paths` | `PROJECT_ROOTS`, separati da `;` | la home dell'utente: i progetti stanno solo qui dentro |
| `secret_key` | `MBARE_PILOT_SECRET_KEY` in chiaro | `None` |

**`.env.example`**: diviso in sezioni (server, segreti, fornitori LLM, cartelle, Postgres, Redis, cache delle automation, Copilot, debug), senza commenti: il significato di ogni variabile è nei docstring di `Config`, in questa doc e nei README. Ci stanno solo le impostazioni che ha senso cambiare: `WORKER_SCRIPT`, `POSTGRES_CONTAINER`, `OPENROUTER_URL` (e `API_APP`, `API_APP_DIR` degli script) si possono ancora impostare, ma di solito basta il default.

**Aggiungere un'impostazione**: un campo in `Config` (con tipo, default e docstring) + la riga nella sezione giusta di `.env.example`. Se è un segreto, `SecretStr | None` e un nome con uno dei marker sopra, così `masked()` lo nasconde.

## Test

`test/unit/test_config.py`: `masked()` con segreti e credenziali negli URL.
