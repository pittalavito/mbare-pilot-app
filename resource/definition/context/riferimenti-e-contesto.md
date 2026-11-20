# Riferimenti e contesto

## Riferimenti
Note collegate a task e attività, che Copilot legge con il task.
- **Riferimento codice** (`code-reference-<titolo>.md`): un pezzo di codice da guardare (repository, file, righe) o il risultato di una ricerca nel codice salvata.
- **Riferimento contesto** (`context-reference-<titolo>.md`): testo copiato da Jira, Confluence o scritto a mano.
Il Segretario li collega per titolo senza leggerli. Cancellare un riferimento lo scollega ovunque.

## Ricerca nel codice
Testo semplice o regex, con filtri sui file (glob) e sul repository; legge i file che git conosce e salta binari, file grandi e `mbare-pilot/`. Agli agenti arrivano poche righe corte e mascherate, mai file interi. Solo Dev salva una ricerca come riferimento codice collegato a un task, con l'ok dell'utente; l'utente lo fa da Progetto → Git, «🔎 Cerca nel codice».

## Contesto del progetto
I documenti di `context/` del progetto (Progetto → Contesto): architettura, convenzioni, decisioni, glossario. Due hanno un ruolo fisso:
- `sviluppo.md`: le regole di sviluppo che il Pianificatore segue per il pre e il post di ogni sviluppo.
- `imparato.md`: quello che le attività chiuse hanno insegnato, in cima il più recente.
Sono indicizzati (RAG) e si cercano con `search_context`.

## Contesto generale
Questi documenti, uguali per tutti i progetti, spiegano come funziona l'app. Anche loro si cercano con `search_context` (origine «generale»). Se il contesto del progetto dice altro, vale il progetto.

## Nomi nascosti
Prima di arrivare a un modello esterno, nomi sensibili (repository, persone, termini del progetto) diventano alias come `REPO_1` o `PERSONA_2`. Gli agenti li usano così come sono: l'app li rimette in chiaro.
