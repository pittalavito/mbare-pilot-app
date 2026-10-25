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
| `app_root`, `run_dir`, `logs_dir` | cartella dell'app, `resource/run`, `resource/logs` | file PID e log di API e worker (gli stessi della UI Streamlit) |
| `files_root` | `data_home / "files"` | note, file caricati e contesto dei progetti (`files/<slug>/`) |
| `definitions_root` | `data_home / "definition"` | agenti, chatbot e automation come YAML (vedi [definitions](../definitions.md)) |
| `project_root_paths` | `PROJECT_ROOTS`, separati da `;` | la home dell'utente: i progetti stanno solo qui dentro |
| `secret_key` | `MBARE_PILOT_SECRET_KEY` in chiaro | `None` |

**Aggiungere un'impostazione**: un campo in `Config` (con tipo, default e docstring) + la riga in `.env.example`. Se è un segreto, `SecretStr | None` e un nome con uno dei marker sopra, così `masked()` lo nasconde.

## Test

`test/unit/test_config.py`: `masked()` con segreti e credenziali negli URL.
