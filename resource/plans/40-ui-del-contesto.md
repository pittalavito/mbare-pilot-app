# UI del contesto più ordinata

Stato: **fatto**.

## Obiettivo
Rendere la pagina Progetto → Contesto più ordinata. Oggi la colonna a sinistra mette in fila tutto: i bottoni per creare i documenti (nuovo, quattro modelli, mappa), i documenti del progetto e i documenti generali. In più «🗺 Genera mappa dei repository» compare sempre e «📐 Regole di sviluppo» può ricomparire anche quando il documento esiste già.

## Cosa cambia (app, solo UI)

### Colonna a sinistra
- **Un solo «➕ Nuovo»** con un menu: documento vuoto, i modelli che il progetto non ha ancora (📐 Regole di sviluppo, 📏 Convenzioni, 📖 Glossario, 🧭 Decisioni) e «🗺 Mappa dei repository», solo se `repository.md` manca.
- **Due gruppi richiudibili, tutti e due chiusi all'apertura della pagina**:
  - «Progetto», con il numero dei documenti;
  - «Generale (da definizioni)», con il numero dei documenti, in sola lettura come oggi.
- **Documenti che l'app usa da sola, in cima al gruppo «Progetto»**, con icona e una riga su chi li usa:
  - 📐 `sviluppo.md`: lo legge il Pianificatore per il pre e il post;
  - 🗺 `repository.md`: la mappa dei repository.

  Sotto, gli altri documenti in ordine alfabetico.

### Mappa dei repository
- Quando `repository.md` esiste, il bottone «🗺 Rigenera» sta in testa al documento aperto e riscrive solo la parte automatica, come oggi.

### Anteprima
- Il documento aperto ha due schede: «✏️ Modifica» (l'area di testo di oggi, con Ctrl+S) e «👁 Anteprima», che lo mostra formattato con il componente `Markdown` già usato nell'app (react-markdown + GFM). L'anteprima mostra il testo che stai scrivendo, anche se non è ancora salvato.
- Anche i documenti generali, in sola lettura, si aprono in anteprima: il testo grezzo resta nell'altra scheda.

### Nomi senza maiuscole
- Modelli, documenti speciali e il controllo «esiste già» confrontano il nome senza badare a maiuscole e minuscole: `Sviluppo.md` conta come `sviluppo.md`, e i bottoni non ricompaiono.
- Anche nel backend: un documento del contesto si legge, si salva e si elimina senza badare alle maiuscole (`ProjectDataService`), così il Pianificatore trova `Sviluppo.md` su ogni disco e la mappa riscrive `Repository.md` invece di crearne un secondo.

## Decisioni prese
- Menu «➕ Nuovo» e due gruppi (non schede, non lista unica con filtro), chiusi di default.
- Mappa: «Rigenera» dal documento aperto, nel menu solo quando manca.
- Documenti dell'app in cima, con icona.
- Anteprima del Markdown con il componente esistente; nessuna libreria nuova (né nel frontend né nel backend).

## Test e documentazione
- vitest di `ContextTab`: il menu mostra solo i modelli che mancano, ignorando le maiuscole; la mappa sta nel menu solo senza `repository.md`, altrimenti «Rigenera» compare sul documento; i documenti speciali sono in cima; i due gruppi partono chiusi e si aprono; l'anteprima mostra il testo non salvato formattato (un titolo, una tabella).
- pytest, se si tocca il Pianificatore: `Sviluppo.md` viene letto.
- Doc: web/README.md (Contesto), la riga di ContextTab nella doc del frontend se c'è.
