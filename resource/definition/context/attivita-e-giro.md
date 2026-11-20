# Attività e giro dei task

Un'attività è una nota (`attivita-<titolo>.md`) con descrizione, todo list (voci con priorità e scadenza), riferimenti e stato (da fare, in corso, fatta). Si apre a step.

## Gli step di un'attività
1. **Descrivi**: titolo, descrizione, voci, riferimenti. Il Segretario aiuta in chat.
2. **Pianifica**: il Pianificatore propone gli agent task per le voci ancora scoperte; l'utente li corregge, li riordina, ne aggiunge a mano e li crea (nascono «da fare»).
3. **Lavora**: il giro porta avanti i task uno alla volta, nell'ordine.
4. **Chiudi**: riepilogo, cosa si è imparato (in cima a `context/imparato.md`), attività fatta.

## Il Pianificatore
Per ogni voce scoperta propone un task (anche per più voci insieme, o senza voci se serve un passo in più). Dentro ogni sviluppo scrive il pre e il post (passi, comandi, automation), seguendo le regole di sviluppo del progetto (`context/sviluppo.md`, sezioni «Prima dello sviluppo», «Dopo lo sviluppo», «Comandi»). Senza regole: pre = branch `feature/<task>` dal branch corrente, aggiornato, build; post = lancia i test. Prima le librerie, poi chi le usa.

## Il giro
Si avvia con «▶️ Avvia» e si ferma con «⏸ Pausa». Lo esegue il worker: al task corrente delega a Copilot e, con l'ok automatico attivo, approva da solo il piano di Copilot; con «Salta da solo pre e post vuoti» salta i pre e post senza comandi né automation. Si ferma dove serve l'utente: il pre e il post di uno sviluppo, rispondere a Copilot, confermare il risultato. Il task corrente è il primo non finito (uno sviluppo è finito quando è fatto e il suo post è fatto o saltato).

## I passi di un task nel giro
- Sviluppo: Pre → Delega a Copilot → Piano di Copilot (l'utente dà l'ok) → Esecuzione → Conferma finale → Post. Pre e post: «🤖 Automatico», «✋ A mano» poi «✅ Fatto», oppure «⏭ Salta».
- Analisi, Confluence, Jira: Delega → Risposta di Copilot (salvata in una nota) → Conferma.
Una delega fallita si può riprovare.

## «📌 Oggi»
Mostra cosa aspetta l'utente: proposte del Pianificatore, voci scadute e in scadenza, attività da chiudere, task fermi su di lui.
