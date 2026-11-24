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
| 32 | [Dove pubblicare su Confluence](32-dove-pubblicare-confluence.md) | fatto | app | Atlassian |
| 33 | [Pubblica nel giro, risultati come riferimenti, archivio](33-pubblica-nel-giro-e-archivio.md) | fatto | app | flusso |
| 34 | [Ricerche salvate e pre/post dentro lo sviluppo](34-ricerche-salvate-e-pre-post-nello-sviluppo.md) | fatto | app | flusso, strumenti |
| 35 | [Presentazione: pagina GitHub Pages e demo live](35-presentazione.md) | fatto | app | presentazione |
| 36 | [Pulizia leggera del codice, docstring e doc per package](36-pulizia-codice-e-doc.md) | fatto | app | pulizia, documentazione |
| 37 | [Niente file del task nei repository, pagina più chiara](37-niente-file-task-nei-repository.md) | fatto | app | copilot, presentazione |
| 38 | [Bacheca di Mbare Pilot modificabile](38-bacheca-modificabile.md) | fatto | app | bacheca |
| 39 | [Struttura di resource e cartelle locali](39-struttura-di-resource.md) | fatto | app | struttura |
| 40 | [UI del contesto più ordinata](40-ui-del-contesto.md) | fatto | app | contesto, UI |
| — | [Backlog](backlog.md) | idee | — | — |

I piani 01-26 sono fatti e sono stati tolti: la storia è nelle PR e nei commit. Il prossimo piano è il 41.

Stati: **da progettare** (mancano decisioni) → **da realizzare** → **in corso** → **fatto**.

## Regole di lavoro

- All'inizio di ogni blocco: una decina di domande a scelta (con idee utili da aggiungere), poi il piano si aggiorna con le decisioni e solo dopo si scrive codice.
- Un branch per sessione, una PR per blocco, in questo repository.
- Ogni modifica con test (pytest coverage ≥ 95%, vitest), `uv run ruff check .`, `uv run mypy`, `npx tsc` in `web/`, documentazione in `docs/doc`.
- Se cambia un tipo di chatbot o un prompt di default, si aggiorna `resource/definition/`: all'avvio l'app allinea da sola agenti, chatbot e automation ai file.

## Il segretario in una riga

Il segretario **tiene in ordine il lavoro, non ci pensa sopra**: modello piccolo, pochi tool fissi, tool in blocco, calcoli nel codice, proposta prima di agire. Il ragionamento resta a Refiner, Architetto, Copilot.
