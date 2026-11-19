# Task pre e post sviluppo

I task pre_dev e post_dev sono il lavoro sui repository prima e dopo uno sviluppo di Copilot. Non vanno mai a Copilot.

## Cosa contengono
- **Passi suggeriti**: a parole, per Dev o per l'utente.
- **Comandi**: uno per riga, lanciati nel repository del task (es. `git checkout -b feature/login`, `mvn -B clean install`).
- **Automation**: una del progetto, lanciata dopo i comandi, con il repository come input.
Li propone il Pianificatore; l'utente li corregge nella scheda del task o allo step Pianifica.

## «🤖 Automatico»
Se il task ha comandi o un'automation, partono senza agente nel worker: prima i comandi uno dopo l'altro, poi l'automation. Al primo errore si ferma e l'errore resta sul passo; il task resta da fare. Finito senza errori il task è fatto e il giro va avanti. Senza comandi né automation, l'automatico apre Dev con la richiesta pronta.

## «✋ A mano»
La dashboard sotto la riga del task: i comandi uno per uno (modificabili, con l'output), l'automation da lanciare, lo stato git, Dev in chat e «✅ Fatto» quando l'utente ha finito.

## Comandi permessi
I comandi girano senza shell (niente `&&`, `|`, `>`, `cd`) in una cartella del progetto, anche se non è un repository git (es. `git init`), mai fuori. Solo quelli della lista dei permessi del progetto (Progetto → Impostazioni). Un comando fuori lista non parte: diventa una richiesta che l'utente approva («Sempre» lo aggiunge alla lista, «Solo stavolta» vale per una volta) o rifiuta.

## Dev
Dev è il chatbot operatore: git sicuro (stato, fetch, branch, checkout, pull solo fast-forward, stash; niente commit né push), `run_command`, allineamento dei pom.xml, test, ricerca nel codice. Quello che fa giusto può diventare un'automation.
