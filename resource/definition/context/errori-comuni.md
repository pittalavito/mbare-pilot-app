# Errori comuni e cosa fare

## Comando non permesso
Il comando non è nella lista dei permessi del progetto: non è partito ed è diventato una richiesta. Dillo all'utente con il comando esatto; lui risponde «Sempre», «Solo stavolta» o «No» (nel pannello dell'agente o sotto la riga del task). Poi si rilancia. Non provare comandi simili per aggirare il permesso.

## Comando fallito
Il comando è partito ed è uscito con un errore. Fermati, riporta le ultime righe dell'output e il codice d'uscita; non rilanciare a caso. L'automatico del pre o del post si ferma al primo errore: il passo resta da fare.

## Delega a Copilot fallita
Il passo «Delega a Copilot» è fallito (repository sbagliato, Copilot non configurato, worker fermo). L'errore è sul passo; si corregge e si preme «🔁 Riprova» o si delega a mano.

## Worker fermo
Il giro, l'automatico e le automation li esegue il worker: se è fermo resta tutto in coda. Si avvia dall'intestazione della pagina («Avvia il worker»).

## Contesto vuoto o non indicizzato
`search_context` non trova niente: il progetto non ha documenti in Progetto → Contesto, o l'indice non si è costruito (manca la chiave dell'embedder). Dillo all'utente invece di inventare; può premere «Reindicizza tutto».

## Copilot fermo o in attesa
Copilot aspetta una risposta (piano da approvare, domanda in chat) o la sessione è fallita. Si risponde nella chat del task; una sessione fallita si rimanda con un messaggio o si delega di nuovo.

## Task nello stato sbagliato
I tool del Refiner lavorano solo su un task «in rifinitura»; la delega vuole un task «da fare». Di' all'utente quale pulsante premere invece di forzare.

## Modifiche non committate
Prima di cambiare branch o aggiornare, se il repository ha modifiche non committate non forzare: chiedi se fare uno stash.
