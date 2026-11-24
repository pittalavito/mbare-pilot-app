# UI del contesto più ordinata

Stato: **da realizzare**.

## Obiettivo
Rendere la pagina Progetto → Contesto più ordinata. Oggi la colonna a sinistra mette in fila tutto: i bottoni per creare i documenti (nuovo, quattro modelli, mappa), i documenti del progetto e i documenti generali. In più «🗺 Genera mappa dei repository» compare sempre e «📐 Regole di sviluppo» può ricomparire anche quando il documento esiste già.

## Cosa cambia (app, solo UI)

### Colonna a sinistra
- **Un solo «➕ Nuovo»** con un menu: documento vuoto, i modelli che il progetto non ha ancora (📐 Regole di sviluppo, 📏 Convenzioni, 📖 Glossario, 🧭 Decisioni) e «🗺 Mappa dei repository», solo se `repository.md` manca.
- **Due gruppi richiudibili**:
  - «Progetto» (aperto), con il numero dei documenti;
  - «Generale (da definizioni)» (chiuso), con il numero dei documenti, in sola lettura come oggi.
- **Documenti che l'app usa da sola, in cima al gruppo «Progetto»**, con icona e una riga su chi li usa:
  - 📐 `sviluppo.md`: lo legge il Pianificatore per il pre e il post;
  - 🗺 `repository.md`: la mappa dei repository.

  Sotto, gli altri documenti in ordine alfabetico.

### Mappa dei repository
- Quando `repository.md` esiste, il bottone «🗺 Rigenera» sta in testa al documento aperto e riscrive solo la parte automatica, come oggi.

### Nomi senza maiuscole
- Modelli, documenti speciali e il controllo «esiste già» confrontano il nome senza badare a maiuscole e minuscole: `Sviluppo.md` conta come `sviluppo.md`, e i bottoni non ricompaiono.
- Da verificare nel backend: il Pianificatore legge `sviluppo.md` con quel nome esatto. Su un disco che distingue le maiuscole, `Sviluppo.md` non verrebbe letto: se serve, lo si cerca senza badare alle maiuscole.

## Decisioni prese
- Menu «➕ Nuovo» e due gruppi (non schede, non lista unica con filtro).
- Mappa: «Rigenera» dal documento aperto, nel menu solo quando manca.
- Documenti dell'app in cima, con icona.

## Test e documentazione
- vitest di `ContextTab`: il menu mostra solo i modelli che mancano, ignorando le maiuscole; la mappa sta nel menu solo senza `repository.md`, altrimenti «Rigenera» compare sul documento; i documenti speciali sono in cima; il gruppo «Generale» parte chiuso e si apre.
- pytest, se si tocca il Pianificatore: `Sviluppo.md` viene letto.
- Doc: web/README.md (Contesto), la riga di ContextTab nella doc del frontend se c'è.
