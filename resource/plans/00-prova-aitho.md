# Prova AITHO GenAI Academy (Blocco 3)

Stato: **traccia**. Collega i requisiti della prova ai piani, fissa la demo e le milestone.

## La prova in breve

Progetto personale, individuale, end-to-end con **datapizza-ai v0.1.0** (l'app lo usa già), che **deve girare** con un README di installazione e avvio. Speech finale di **10 minuti**: problema e contesto, cosa ho fatto, demo, **cosa ho imparato e dove ho avuto difficoltà**. Solo dati pubblici o miei: niente dati riservati AITHO (per la demo: un progetto di prova pubblico).

## Requisiti → piani

| Requisito | Dove | Note |
|---|---|---|
| LLM & prompt con datapizza-ai | 02 | una chiamata con risposta strutturata, prompt progettato e misurato |
| RAG su una base di conoscenza | 04 | contesto del progetto su pgvector (embedder già presente) |
| Autonomia: agente / multi-agente con MCP | 01, 03, 05 | segretario → Refiner → Copilot; Architetto; server MCP dell'app |
| Osservabile | 06 | log già presenti (`core/observability.py`); in più costo e latenza per chiamata |
| Almeno un guardrail | 02 | mascheramento dei dati sensibili + anteprima; divieti git di Copilot (già presenti) |
| README che spiega install e avvio | app `README.md` | già presente: va verificato da zero su macchina pulita |

### Cosa alza il livello

| Punto | Dove |
|---|---|
| RAG conversazionale con memoria | 04: il chatbot che cerca nel contesto ricorda la conversazione (le conversazioni esistono già) |
| Valutazione con i dati | 06: costo, latenza, qualità Elabora WIP, qualità RAG |
| Multi-agente reale / MCP usato da un altro host | 03: lo stesso server MCP usato da Copilot CLI e da Claude Desktop |
| UI minima o demo live | già presente (FastAPI + React) |
| Copilot consapevole con AGENTS.md | da scrivere: `AGENTS.md` nella root dell'app (sotto) |

## La demo (10 minuti)

1. **Problema** (1'): lavoro su più progetti e repository, appunti sparsi, task da delegare a un agente di coding senza dargli dati sensibili.
2. **WIP → attività** (2'): scrivo una WIP con un nome e un'email, anteprima mascherata, «Elabora WIP», confermo le proposte.
3. **Attività → agent task → Refiner con RAG** (2'): creo un task da una voce, il Refiner lo rifinisce cercando nel contesto del progetto, lo porto a «da fare».
4. **Copilot con MCP** (2'): delego; Copilot legge task e contesto dai tool MCP, dichiara «fatto», il task va «da verificare», la voce si spunta a «fatto».
5. **Stesso MCP da Claude Desktop** (1'): chiedo lo stato del progetto.
6. **Numeri** (1'): costo e latenza per chiamata, qualità WIP e RAG sul set di prova.
7. **Imparato e difficoltà** (1').

## Milestone

| Entro | Dove essere | Piani |
|---|---|---|
| S12 | idea, progetto di prova pubblico, primo prompt che gira | 01, 02 (chiamata e schema) |
| S13 | RAG + autonomia | 04, 03 |
| S14 | prototipo e test | 02 completo, 06 |
| S15 | guardrail, sistema completo, README, prove della demo | 05 (se c'è tempo), rifiniture |

## AGENTS.md

Da scrivere nella root di `mbare-pilot-app`, letto da Copilot quando lavora sull'app stessa:

- struttura (`src/` per package, `web/`, `resource/doc/` un README per package);
- comandi: `uv run pytest`, `uv run ruff check .`, `uv run mypy`, `npx tsc` e `npx vitest` in `web/`;
- regole: coverage ≥ 95%, documentazione aggiornata con il codice, niente dati sensibili nei test, italiano nella UI e nei documenti;
- dove stanno le definizioni (questo repository) e quando vanno aggiornate.

## Da decidere

- Il progetto di prova pubblico per la demo (un repository open source con qualche modulo e documentazione).
- Se registrare un video di riserva della demo.

## Diario per lo speech

Da riempire strada facendo (alimenta «cosa ho imparato» e «difficoltà»):

- …
