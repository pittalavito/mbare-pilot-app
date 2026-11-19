# Piani di lavoro

Piani dell'app **mbare-pilot**: da qui (piano 28) tutto sta in questo repository, codice, definizioni di default (`resource/definition/`) e piani. L'app **non legge** questa cartella.

Ogni piano descrive **cosa fare**, non com'è fatto oggi; le parti che esistono già sono indicate come tali. Struttura comune: Obiettivo, Cosa cambia (app / definizioni), Decisioni prese, Da decidere, Test e documentazione.

## Ordine e stato

| # | Piano | Stato | Repo toccati | Per la prova |
|---|---|---|---|---|
| 00 | [Prova AITHO](00-prova-aitho.md) | traccia | — | requisiti, demo, AGENTS.md |
| 27 | [Contesto più utile agli agenti](27-contesto-piu-utile.md) | fatto | app + definizioni | RAG |
| 28 | [Un solo repository](28-un-solo-repo.md) | fatto | app | pulizia |
| 29 | [Cosa vede il modello](29-cosa-vede-il-modello.md) | fatto | app | guardrail, osservabilità |
| 30 | [Bacheca di Mbare Pilot](30-bacheca-mbare-pilot.md) | fatto | app | demo |
| 31 | [Costi dell'embedding](31-costi-embedding.md) | fatto | app | osservabilità, costo |
| — | [Backlog](backlog.md) | idee | — | — |

I piani 01-26 sono fatti e sono stati tolti: la storia è nelle PR e nei commit. Il prossimo piano è il 32.

Stati: **da progettare** (mancano decisioni) → **da realizzare** → **in corso** → **fatto**.

## Regole di lavoro

- All'inizio di ogni blocco: una decina di domande a scelta (con idee utili da aggiungere), poi il piano si aggiorna con le decisioni e solo dopo si scrive codice.
- Un branch per sessione, una PR per blocco, in questo repository.
- Ogni modifica con test (pytest coverage ≥ 95%, vitest), `uv run ruff check .`, `uv run mypy`, `npx tsc` in `web/`, documentazione in `resource/doc`.
- Se cambia un tipo di chatbot o un prompt di default, si aggiorna `resource/definition/`: all'avvio l'app allinea da sola agenti, chatbot e automation ai file.

## Il segretario in una riga

Il segretario **tiene in ordine il lavoro, non ci pensa sopra**: modello piccolo, pochi tool fissi, tool in blocco, calcoli nel codice, proposta prima di agire. Il ragionamento resta a Refiner, Architetto, Copilot.
