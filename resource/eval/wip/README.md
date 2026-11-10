# Set di prova di «Elabora WIP»

Ogni file `.json` è un caso: la WIP, le attività che ci sono già, i valori sensibili che **non** devono arrivare al modello e le proposte attese.

- `today` (facoltativo): la data di oggi per il caso, `YYYY-MM-DD` (default 2026-11-10).
- `wip`: il testo della nota (senza segni: tutto nuovo).
- `activities`: le attività del progetto, come `{title, items: [{text, done}]}`.
- `map`: i termini già nella mappa del progetto (`{category, value}`).
- `sensitive`: i valori che non devono mai comparire nel testo mandato al modello.
- `expected`: le proposte attese, come le scriverebbe un buon modello (`kind`, e `title`, `activity_title`, `item` o `text`).

Li usano i test (`test/unit/service/test_wip_service.py`: niente fughe di dati sensibili, con un modello finto) e la valutazione (`service/evaluation_service.py`: script `resource/scripts/eval-wip.py` o pulsante in Admin → Observability → Metriche), che misura uno o più modelli veri.

Una proposta è giusta quando ha lo stesso tipo dell'attesa, la stessa attività (`activity_title`) e la stessa voce (`item`, la posizione nella todo list completa) o un testo simile (almeno metà delle parole dell'attesa, confrontate per radice).
