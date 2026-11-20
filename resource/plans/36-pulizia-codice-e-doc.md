# Pulizia leggera del codice, docstring e doc per package

Stato: **fatto**.

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

## Come è fatto
- Codice morto trovato con vulture (Python) e ts-prune (frontend): due metodi Python mai chiamati, due hook e una funzione del frontend, 27 tipi esportati e mai usati.
- La scelta «Proponila quando delego a Copilot (preparazione)» in «fanne un'automation» non aveva più effetto: tolta dalla UI (il campo `purpose` resta nell'API).
- Docstring e commenti: via i riferimenti ai piani («plan N», «blocco N»), via «Prepara sviluppo» e «Verifica sviluppo» (anche nelle descrizioni dei tool e in due testi della UI).
- Doc: riscritte `service`, `tool`, `controller`, `core`, `domain/project`, `definitions.md`, `web/README.md` (l'elenco completo degli endpoint ora è solo nello Swagger); corrette le altre dove erano rimaste indietro.

## Test e documentazione
- Tutti i test restano verdi senza cambiarli, salvo quelli del codice tolto. Coverage ≥ 95%, ruff, mypy, tsc.
- Una PR sua.
