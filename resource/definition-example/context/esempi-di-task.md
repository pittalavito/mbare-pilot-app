# Esempi di task ben fatti

Un esempio per tipo: obiettivo chiaro, criteri verificabili, vincoli espliciti. Sono la misura a cui il Refiner porta un task e il modello che il Pianificatore segue.

## Esempio di sviluppo
- **Titolo**: Aggiungi l'OTP al login
- **Obiettivo**: dopo la password il login chiede un codice OTP inviato per SMS; senza codice valido l'accesso è negato.
- **Criteri**: il codice scade dopo 5 minuti; tre tentativi sbagliati bloccano l'utente per 15 minuti; test di unità per scadenza e blocco; i test esistenti restano verdi.
- **Vincoli**: niente nuove dipendenze; il servizio SMS si usa tramite l'interfaccia che c'è già.

## Esempio di analisi
- **Titolo**: Capire come si calcolano le tariffe portuali
- **Obiettivo**: una nota che spiega da dove parte il calcolo, quali classi e tabelle coinvolge e dove si applicano gli sconti.
- **Criteri**: il percorso dalla chiamata REST al risultato; l'elenco dei file con una riga ciascuno; i punti fragili.
- **Vincoli**: non cambiare il codice.

## Esempio di pagina Confluence
- **Titolo**: Bozza della pagina «Rilascio del modulo pagamenti»
- **Obiettivo**: una pagina per chi rilascia: prerequisiti, passi, verifiche, rollback.
- **Criteri**: segue il template delle pagine di rilascio; ogni passo ha il comando o la schermata; c'è la sezione rollback.
- **Vincoli**: niente segreti né indirizzi interni nella pagina.

## Esempio di issue Jira
- **Titolo**: Rifinisci NAV-412 «Errore sul cambio porto»
- **Obiettivo**: la issue dice come riprodurre, cosa ci si aspetta e cosa succede, con i criteri per chiuderla.
- **Criteri**: passi di riproduzione numerati; risultato atteso e ottenuto; criteri di accettazione verificabili.

## Esempio di pre sviluppo
- **Titolo**: Prepara il branch per l'OTP
- **Passi**: branch dal develop aggiornato; build della libreria di autenticazione e poi dell'api.
- **Comandi**: `git fetch --all --prune`, `git checkout -b feature/otp-login`, `mvn -B clean install`.

## Esempio di post sviluppo
- **Titolo**: Pulisci e testa dopo l'OTP
- **Passi**: togli la cartella del task per Copilot; lancia i test toccati; commit e push li fa l'utente.
- **Comandi**: `rm -rf mbare-pilot/agent-task-aggiungi-l-otp-al-login`; poi i test con `run_tests` oppure `mvn -B test`.
