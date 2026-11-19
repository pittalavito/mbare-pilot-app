# Costi dell'embedding

Stato: **fatto**.

## Obiettivo

Vedere nelle Metriche quanto costano le chiamate all'embedder remoto del RAG (indicizzazione e ricerche), oggi non conteggiate.

## Decisioni prese
- L'embedder remoto (OpenRouter) restituisce anche i token contati dal provider; quello locale (`hashing`) è gratis e non si conta.
- Ogni chiamata si registra (tabella `embedding_usage`: progetto, modello, scopo `index`/`search`, token, costo stimato).
- Il costo è una stima da una tabella di prezzi nel codice (`EMBEDDING_EUR_PER_1M`); un modello sconosciuto costa 0.
- Nelle Metriche, accanto a Copilot ed Elabora WIP, «Embedding del RAG (costo stimato)»: chiamate, token e costo per modello e scopo, con gli stessi filtri di periodo e progetto.

## Test e documentazione
- pytest: token e costo registrati per indicizzazione e ricerca, filtri; l'embedder locale non registra niente.
- vitest: la sezione nelle Metriche.
- Doc `service`.
