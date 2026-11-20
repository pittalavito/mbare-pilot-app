# Pulizia leggera del codice, docstring e doc per package

Stato: **da realizzare** (dopo il 35).

## Obiettivo
Codice e documentazione più snelli e allineati, senza cambiare cosa fa l'app.

## Decisioni prese
- **Pulizia leggera del codice** (Python e frontend):
  - via il codice morto (funzioni, campi, rami ed endpoint che nessuno usa più);
  - via i resti dei vecchi flussi (task pre/post, automation di sistema);
  - via i duplicati evidenti.
  - Niente cambi di comportamento, di API o di schema del DB.
- **Docstring Python**: corte e attuali. Dicono cosa fa e le regole che non si vedono dal codice, senza storia dei piani né frasi ripetute.
- **Doc per package** (`docs/doc`): un README per package (`core`, `controller`, `service`, `domain/...`, `models`, `tool`, `config`, definizioni) e `web/README.md`.
  - **Sincronizzata** col codice di oggi.
  - **Minimizzata**: cosa fa il package, i file principali, le regole, in elenchi brevi. Il dettaglio sta nelle docstring.

## Test e documentazione
- Tutti i test restano verdi senza cambiarli, salvo quelli del codice tolto. Coverage ≥ 95%, ruff, mypy, tsc.
- Una PR sua.
