# Pre e post di uno sviluppo

Ogni task di sviluppo ha due passi in più, fuori da Copilot: il **pre** (prima della delega: branch, aggiornamento, build) e il **post** (dopo la conferma finale: test, pulizia, commit se le regole lo dicono). Non ci sono più task pre o post sviluppo a parte. I passi di uno sviluppo nel giro sono: Pre → Delega → Piano di Copilot → Esecuzione → Conferma finale → Post.

## Cosa contengono
Pre e post hanno ognuno:
- **Passi**: a parole, per Dev o per l'utente.
- **Comandi**: uno per riga, lanciati nel repository del task (es. `git checkout -b feature/login`, `mvn -B clean install`).
- **Automation**: una del progetto, lanciata dopo i comandi, con il repository come input.
Li propone il Pianificatore dentro ogni sviluppo, dalle regole di `context/sviluppo.md`; l'utente li corregge nella scheda del task (sezioni Pre e Post) o allo step Pianifica.

## Come si fanno
Il pre e il post ci sono sempre: il giro si ferma lì finché l'utente non sceglie.
- **«🤖 Automatico»**: se ci sono comandi o un'automation partono senza agente nel worker, prima i comandi uno dopo l'altro, poi l'automation. Al primo errore si ferma e l'errore resta sul passo. Finito senza errori il passo è fatto e il giro va avanti. Senza comandi né automation apre Dev con la richiesta pronta.
- **«✋ A mano»**: la dashboard sotto la riga del task: i passi, i comandi uno per uno (modificabili, con l'output), l'automation da lanciare, lo stato git, Dev in chat e «✅ Fatto» quando l'utente ha finito.
- **«⏭ Salta»**: questa volta non c'è niente da fare.
- Opzione del giro **«Salta da solo pre e post vuoti»**: quelli senza comandi né automation li salta il giro da solo.
Il task è fatto con la conferma finale; il giro passa al task dopo quando anche il post è fatto o saltato. Un task delegato senza passare dal pre ha il pre saltato.

## Comandi permessi
I comandi girano senza shell (niente `&&`, `|`, `>`, `cd`) in una cartella del progetto, anche se non è un repository git (es. `git init`), mai fuori. Solo quelli della lista dei permessi del progetto (Progetto → Impostazioni). Un comando fuori lista non parte: diventa una richiesta che l'utente approva («Sempre» lo aggiunge alla lista, «Solo stavolta» vale per una volta) o rifiuta.

## Dev
Dev è il chatbot operatore: git sicuro (stato, fetch, branch, checkout, pull solo fast-forward, stash; niente commit né push), `run_command`, allineamento dei pom.xml, test, ricerca nel codice. Quello che fa giusto può diventare un'automation.
