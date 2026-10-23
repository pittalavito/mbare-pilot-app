# Mbare Pilot

App agentica per lavorare su **progetti** (cartelle del PC).

## Avvio rapido

Prerequisiti: Python 3.12, [uv](https://docs.astral.sh/uv/).

1. Copia `.env.example` in `.env`
2. Avvia la UI:

```bash
python resource/scripts/run-ui.py
```

## UI

Frontend in `ui/`: parla **solo** con l'API del backend (`API_URL`), parte su `UI_PORT`.

- **Progetti**: Chat, Automation, Dati, Git, Impostazioni (Atlassian, agenti del progetto)
- **Libreria**: agenti, ruoli, prompt versionati, tool globali
- **Admin**: Servizi, Observability, Modelli

API e worker si accendono e spengono dal pannello **Backend** nella barra laterale (stato, ▶/⏹, log). Restano attivi anche se ricarichi o riavvii la UI (PID in `resource/run/`, log in `resource/logs/`).

## Backend

In arrivo.

## Documentazione

- [UI: struttura e nuove pagine](resource/doc/ui.md)
