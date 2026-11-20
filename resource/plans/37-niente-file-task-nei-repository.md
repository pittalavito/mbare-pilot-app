# Niente file del task nei repository, pagina più chiara

Stato: **fatto**.

## Obiettivo
1. Nei repository delegati a Copilot non resta niente: oggi l'app ci lascia `mbare-pilot/<task>/task.md`.
2. La pagina GitHub Pages spiega meglio come lavorano insieme agenti, tool, automation e Claude Code, e il launcher.

## Decisioni prese

### Niente file del task
- L'app **non scrive più niente nel repository**: il prompt dice a Copilot il nome del task, e lui lo legge (con i riferimenti) dal server MCP dell'app, come già fa.
- Nei prompt di Copilot il segnaposto `{task_folder}` diventa **`{task}`**, il nome del task (`global-coding-agent.yml` e `coding-agent/*.md`), e sparisce «non modificare i file di …».
- Le sessioni senza repository lavorano ancora nella loro cartella dei dati del progetto, ma senza il file del task.
- Via il modulo `task_folder`, il filtro di quella cartella nelle ricerche, nei file cambiati e nei test toccati, e il passo «togli la cartella mbare-pilot/<task>/» nel post (regole di default del Pianificatore, contesto generale).
- Le cartelle già nei repository le cancelli tu una volta: l'app non le tocca più.

### Pagina
- Una sezione **«Come lavorano insieme»**: gli agenti usano i tool del registro unico; Dev fa una procedura in chat e, se è giusta, diventa un'automation; l'Architetto progetta le automation con i tool che ci sono; quando manca un tool scrive una richiesta, e **Claude Code** la lavora dal server MCP dev, scrive il tool con i test e apre la PR; dopo il merge il tool è nel catalogo.
- Una sezione **«Launcher»**: la pagina nel browser che avvia e ferma l'app (Docker, frontend, API) senza terminali, e parte da sola all'accesso.
- Una sezione **«Tutto configurabile»**: definizioni a tre livelli (app, cartella dati, progetto), agenti e chatbot creati dalla UI, prompt versionati, modelli, regole del progetto.
- Una sezione **«Come è stato costruito»**: con Claude Code in un ambiente isolato, domande, piano, «vai», PR e CI, merge dopo la lettura del codice. Claude non ha mai visto il progetto del cliente su cui ho sperimentato.

## Test e documentazione
- pytest: prompt con `{task}`, nessun file scritto nel repository (avvio, turni, cambio di repository, esecuzione), file cambiati e ricerca senza filtri speciali.
- Pagina provata nel browser (chiaro, scuro, telefono).
- Doc (`docs/doc`), definizioni e contesto generale aggiornati.
