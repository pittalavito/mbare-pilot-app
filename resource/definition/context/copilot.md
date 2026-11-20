# Copilot

Copilot (GitHub Copilot CLI) è l'agente che lavora sul codice. Riceve un agent task delegato e lavora in un repository del progetto.

## La delega
Si delega un task da fare: sviluppo, analisi, Confluence o Jira (il pre e il post di uno sviluppo non vanno mai a Copilot). Si sceglie il repository; un task senza codice può partire senza repository (Copilot lavora nei dati del progetto). Nel repository l'app non scrive niente: il prompt dice a Copilot il nome del task, e lui lo legge con i suoi riferimenti dal server MCP dell'app. Il repository della delega si può cambiare finché la sessione non è mai partita.

## Piano ed esecuzione
Il primo turno è un piano: Copilot dice cosa farà e l'utente risponde in chat («Ok, parti» o correzioni). Poi esegue; finita l'esecuzione il task è «da verificare». L'utente controlla e conferma (il task è fatto) o rimanda a Copilot con un messaggio.

## Cosa può fare Copilot
Legge il task, i riferimenti collegati e il contesto del progetto (via MCP), chiede all'utente quando serve. Alcuni comandi gli sono vietati (in `global-coding-agent.yml`). Costa crediti AI: il riepilogo dell'attività li conta.
