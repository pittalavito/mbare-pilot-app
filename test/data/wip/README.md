# Set di prova di «Elabora WIP»

Ogni file `.json` è un caso: la WIP, le attività che ci sono già, i valori sensibili che **non** devono arrivare al modello e le proposte attese.

- `wip`: il testo della nota (senza segni: tutto nuovo).
- `activities`: le attività del progetto, come `{title, items: [{text, done}]}`.
- `map`: i termini già nella mappa del progetto (`{category, value}`).
- `sensitive`: i valori che non devono mai comparire nel testo mandato al modello.
- `expected`: le proposte attese, come le scriverebbe un buon modello (`kind`, e `title`, `activity_title`, `item` o `text`).

Li usano i test (`test/unit/service/test_wip_service.py`: niente fughe di dati sensibili, con un modello finto) e, nel blocco delle metriche, lo script che misura un modello vero.
