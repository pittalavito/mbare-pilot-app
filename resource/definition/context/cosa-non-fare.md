# Cosa non fare

Le regole di sicurezza di tutti gli agenti, in un posto solo.

## Mai senza l'ok dell'utente
- Portare un task a «da fare» (Refiner), salvare una ricerca come riferimento (Dev), inviare una richiesta di tool (Architetto).
- Lanciare un comando fuori dalla lista dei permessi: lo approva l'utente.
- Fare uno stash o cambiare branch con modifiche in corso.

## Mai
- Commit e push dagli agenti: li fa l'utente o una regola esplicita del progetto.
- Cancellare o rinominare attività e task (Segretario).
- Leggere il contenuto dei riferimenti quando il tool dà solo i titoli (Segretario).
- Dire che un'automation è salvata: la salva l'utente con il pulsante (Architetto).
- Inventare tool, argomenti, nomi di file, risultati di comandi o contenuti del contesto.
- Togliere o cambiare gli alias come `REPO_1`, `PERSONA_2`: si usano così come sono.
- Scrivere segreti (password, token, chiavi) in note, task o riferimenti.

## Quando non sai
Cerca nel contesto; se non c'è, chiedi all'utente o di' che non lo sai.
