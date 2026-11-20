# Agent task: tipi e stati

Un agent task è una nota del progetto (`agent-task-<titolo>.md`) che descrive un lavoro da fare. Lo creano l'utente, il Segretario o il Pianificatore.

## Tipi di task
- **development**: uno sviluppo che cambia il codice. Lo esegue Copilot, tra il suo pre e il suo post.
- **analysis**: un'analisi del codice. Copilot risponde con una nota (`analisi-<task>.md`), non cambia il codice.
- **confluence**: la bozza di una pagina Confluence. Copilot scrive la bozza in una nota (`bozza-<task>.md`).
- **jira**: la rifinitura di una issue Jira. Copilot scrive la bozza in una nota.

## Campi di un task
Titolo, tipo, obiettivo, contesto, criteri di accettazione (una checklist), vincoli, riferimenti collegati. Uno sviluppo ha in più il **pre** (prima della delega: branch, aggiornamento, build) e il **post** (dopo la conferma: test, pulizia, commit se le regole lo dicono), ognuno con passi a parole, comandi (uno per riga) e un'automation del progetto; mai Copilot. Uno sviluppo può dire quali test lanciare (tutti o solo quelli toccati).

## Stati
- **creato**: appena scritto, ancora da rifinire.
- **in rifinitura**: l'utente l'ha aperto con «Rifinisci con il Refiner»; il Refiner lavora solo in questo stato.
- **da fare**: rifinito, pronto per il giro o per la delega.
- **in corso**: Copilot ci sta lavorando.
- **da verificare**: Copilot ha finito; l'utente controlla e conferma.
- **fatto**: concluso. Quando un task diventa fatto, la voce dell'attività da cui è nato si spunta da sola.

## La rifinitura
Ogni tipo ha una checklist di cosa deve avere il task (es. per uno sviluppo: obiettivo chiaro, criteri verificabili, vincoli). Il Refiner legge il task, cerca nel contesto, fa poche domande, scrive obiettivo, contesto, criteri e vincoli, e solo dopo un sì esplicito dell'utente lo porta a «da fare». Titolo, tipo e riferimenti li cambia l'utente.

## Task e voci delle attività
Un task può nascere da una o più voci della todo list di un'attività: la voce mostra `→ agent-task-….md` e si spunta quando il task è fatto (si despunta se il task torna indietro). Cancellare il task toglie il collegamento.
