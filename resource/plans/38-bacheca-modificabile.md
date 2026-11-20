# Bacheca di Mbare Pilot modificabile

Stato: **fatto**.

## Obiettivo
Tracciare dalla UI le modifiche future di Mbare Pilot: la bacheca «🚀 Mbare Pilot» smette di essere in sola lettura.

## Decisioni prese
- **Dove si salva**: in `roadmap.yml`, che la UI scrive nella tua cartella dati (`<MBARE_PILOT_HOME>/definition/roadmap.yml`), come i chatbot salvati dalla UI. Il default dell'app resta il punto di partenza. Niente database.
- **Schede**: titolo, descrizione, stato (Da fare, In corso, Fatto), più:
  - **tipo**, con colore: bug, funzione, refactoring, documentazione, integrazione, più quelli di oggi (uso, progettazione, rag);
  - **priorità**: alta, media, bassa; in ogni colonna prima le alte;
  - **chi la fa**: tu, Claude, Copilot, agente remoto.
  La fattibilità resta, facoltativa.
- **Dalla UI**: «➕ Nuova scheda», si apre una scheda per modificarla o eliminarla, e si **trascina** tra le colonne (drag and drop del browser, senza librerie nuove). In ogni scheda anche il menu «Sposta» per chi non vuole trascinare.
- **Testata**: traguardo e visione restano e si modificano dalla UI.
- Le 6 attività future di oggi restano com'erano.
- Ogni scheda ha un `id` stabile (scritto nel file), così due schede con lo stesso titolo non si confondono.

## Test e documentazione
- pytest: lettura (file tuo o dell'app), salvataggio nella cartella dati, nuova scheda, modifica, spostamento, eliminazione, file rotto, id stabili.
- vitest: nuova scheda, modifica, eliminazione, trascinamento e «Sposta», testata modificabile.
- Doc: `definitions.md`, `service`, `controller`, `web/README.md`.
