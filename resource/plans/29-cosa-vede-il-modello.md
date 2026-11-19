# Cosa vede il modello

Stato: **fatto**.

## Obiettivo

Una finestra che mostra, leggibile, tutto quello che è entrato e uscito dal modello in una run di un agente, nella versione mascherata (quella che ha visto il modello) e in chiaro.

## Decisioni prese

### Dove si apre
- **Sotto ogni risposta in chat** (Segretario, Refiner, Dev, Architetto e i chatbot personalizzati): «🔍 Cosa ha visto il modello».
- **Dalle esecuzioni** in Admin / Osservabilità: dalla riga di una run.

### Cosa mostra
- **System prompt** come l'ha ricevuto il modello (con l'elenco dei documenti di contesto).
- **Input e storia**: il messaggio e i messaggi precedenti della conversazione.
- **Chiamate ai tool**, in ordine: nome, argomenti, risultato (o errore).
- **Risposta** finale.

### Mascherato e in chiaro
- Un interruttore **Mascherato / In chiaro** cambia tutte le sezioni insieme; nella versione mascherata gli alias (`REPO_1`, `PERSONA_2`…) sono evidenziati.
- La run salva la versione **mascherata** (quella uscita davvero verso il modello); quella in chiaro si ricava alla lettura con la mappa del progetto.

### Formato
- Una sezione a fisarmonica per parte; il testo come markdown, i JSON dei tool indentati; «Copia» su ogni blocco.

## Deciso in realizzazione
- Anche gli agenti con risposta strutturata (Pianificatore, WIP, Imparato, Bozza attività) salvano la trascrizione: la si apre dalla loro run in Osservabilità.
- Nella versione in chiaro input e risposta sono quelli della run (già in chiaro, anche gli alias temporanei del riconoscimento automatico); il resto si rimette in chiaro con la mappa del progetto.

## Test e documentazione

- pytest: la run salva prompt, storia, input, tool e risposta mascherati; l'API li restituisce mascherati e in chiaro; run senza progetto (niente maschera).
- vitest: «🔍» in chat e dalle esecuzioni; interruttore; sezioni; copia.
- Doc `service`, `controller`, `web/README.md`.
