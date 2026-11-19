# Pubblica nel giro, risultati come riferimenti, archivio

Stato: **da realizzare**.

## Obiettivo

L'essenziale per lavorare pulito: pubblicare la bozza di Copilot dal giro senza entrare in Note, passare il risultato di un task al successivo, un tipo di task più leggibile, archiviare le attività fatte.

## Decisioni prese

### Pubblica nel giro (niente task nuovo)
- Un task Confluence o Jira, dopo la risposta di Copilot salvata come bozza, ha il passo **«Pubblica»** nello step Lavora: «📤 Pubblica» apre la finestra con la bozza **modificabile**, l'anteprima, dove metterla (piano 32) e «Pubblica».
- Lo stesso pulsante sta nella chat di Copilot del task.
- Dopo la pubblicazione il task è fatto, la pagina o issue diventa un riferimento e **la bozza si cancella da sola**.

### Il risultato passa al task dopo
- Quello che un task produce (la nota di un'analisi, la pagina o issue pubblicata) diventa un riferimento e **si collega da solo al task successivo** dell'attività.
- Non tutti i riferimenti vanno portati dietro: in **Pianifica** e nella **scheda del task** si tolgono quelli che non servono (✕).

### Tipo del task
- Un **menu a tendina** con i 6 tipi e una riga di spiegazione ciascuno, al posto dei pulsanti affiancati.

### Archivio
- Allo step **Chiudi**, dopo «Chiudi attività», **«🗄 Archivia»**:
  - resta una **nota riassunto** `archivio-<attività>.md`: titolo, date, voci, task fatti (titolo, tipo, esito, link a pagine, issue e note);
  - si cancellano attività, task, bozze, piano e sessioni di Copilot;
  - per i **riferimenti** collegati si sceglie: cancellarli tutti, nessuno o solo alcuni (caselle).
- In Lavoro una scheda **«🗄 Archivio»** con le note riassunto.

## Test e documentazione
- pytest: passo «Pubblica» del giro; bozza cancellata dopo la pubblicazione; risultato collegato al task successivo; archivio (nota, cosa si cancella, riferimenti scelti).
- vitest: «📤 Pubblica» in Lavora e nella chat di Copilot con la bozza modificabile; ✕ sui riferimenti; menu del tipo; «🗄 Archivia» e scheda Archivio.
- Doc `service`, `controller`, `web/README.md`.
