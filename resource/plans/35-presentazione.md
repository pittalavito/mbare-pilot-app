# Presentazione: pagina GitHub Pages e demo live

Stato: **da realizzare**.

## Obiettivo
Presentare Mbare Pilot in due parti: una **pagina** che lo racconta a grandi linee e un **flusso live** su un'attività vera.

## Decisioni prese
- La pagina sta in `docs/index.html` di questo repo (pubblico), pubblicata da GitHub Pages dal branch `main`, cartella `/docs`. È statica: niente build, niente dipendenze.
- È **una pagina a sezioni** che scorre, con **solo diagrammi** in SVG dentro la pagina e nessuno screenshot: l'app si fa vedere dal vivo.
- Sezioni:
  1. **Il problema**: il lavoro di tutti i giorni sparso tra Jira, Confluence, repository e agenti.
  2. **La soluzione**: attività → Pianificatore → giro dei task con Copilot, Dev e te; le persone decidono nei punti di controllo.
  3. **Architettura**: diagramma con FastAPI, worker, Postgres e pgvector, Redis, React, Copilot via MCP, Atlassian, LLM via OpenRouter.
  4. **Tecnologie**: Python, FastAPI, datapizza-ai, SQLModel, React, Vite, Mantine, Docker.
  5. **Agenti**: Segretario, Refiner, Pianificatore, Dev, Copilot, Architetto, più gli agenti piccoli con risposta strutturata. Contesto generale e del progetto nel RAG.
  6. **Osservabilità**: run, costi, token, tracce, «Cosa ha visto il modello».
  7. **Masking**: i nomi del cliente sostituiti da alias prima di uscire, poi rimessi in chiaro.
  8. **Automation**: come funzionano (grafi di step, tool senza LLM), detto chiaro che oggi non le usi.
  9. **Visione**: uno strumento per i colleghi di Aitho, con login e utenti e le PR al progetto aperte dall'app.
- Il link alla pagina va nel `README.md`.

## Scaletta della demo (fuori dal codice)
1. La pagina, 5 minuti.
2. Live:
   1. «➕ Nuova attività» → «📎 Parto da riferimenti», con «Cosa vuoi fare»;
   2. il Pianificatore propone i task, con pre e post dentro gli sviluppi;
   3. il giro: uno sviluppo con Copilot e un task Jira o Confluence (lettura, bozza, «📤 Pubblica»);
   4. «🔍 Cosa ha visto il modello» e Osservabilità.
3. Le automation, solo un accenno.
4. La visione.

## Da fare dopo, a mano
- In GitHub → Settings → Pages: Source «Deploy from a branch», branch `main`, cartella `/docs`.

## Test e documentazione
- La pagina si controlla aprendola nel browser (Playwright): chiaro e scuro, larghezza del telefono, niente scroll orizzontale.
- `README.md` con il link. Niente codice dell'app cambiato.
