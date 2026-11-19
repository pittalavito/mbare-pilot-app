# Un solo repository

Stato: **fatto**.

## Obiettivo

Tenere tutto in `mbare-pilot-app`: le definizioni di default vivono nell'app, versionate con il codice, e si aggiornano da sole; la cartella dati serve solo a quello che cambi tu. Il repository `mbare-pilot-definition` si archivia.

## Decisioni prese

### Dove stanno le definizioni
- **Default nell'app**: `resource/definition/` (agenti, chatbot, automation, `global-coding-agent.yml`, `coding-agent/`, `context/`), letta direttamente dall'app. Prende il posto di `resource/definition-example/`.
- **Cartella dati** `MBARE_PILOT_HOME/definition/`: solo quello che cambi tu e i file dei progetti (`project/<slug>/`, come oggi).
  - Nei file YAML (agenti, chatbot, automation) si fondono **per nome**: un elemento con lo stesso nome vince su quello dell'app, gli altri restano quelli dell'app (il tuo `global-chat-bots.yml` può contenere solo il Refiner cambiato).
  - Nei file markdown (`context/`, `coding-agent/`) lo **stesso percorso vince** su quello dell'app.
- Niente più `init-definitions.py` né copia degli esempi.

### Aggiornamento
- **All'avvio** l'app allinea agenti, chatbot e automation di default ai file (app + tue modifiche); quelli creati da te in UI non si toccano. «Sincronizza da file» resta per forzarlo senza riavviare.
- **La UI scrive il file**: salvare dalla UI un default (es. il prompt del Refiner) scrive quell'elemento nella cartella dati: diventa «tuo» e vince sull'app, anche dopo il riavvio. **«↩ Torna al default»** lo toglie dalla cartella dati e torna quello dell'app.

### Nella UI
- Un badge sull'origine di ogni definizione (Impostazioni → Definizioni da file, contesto generale): **app**, **tuo** (cartella dati) o **progetto**.

### Piani e repository
- I piani vanno in `mbare-pilot-app` (`resource/plans/`); da qui in poi **una PR per blocco in un solo repository**.
- Dopo il merge `mbare-pilot-definition` si archivia su GitHub (lo fai tu).
- Niente retrocompatibilità: si ricrea il database e si svuota la cartella `definition/` dei dati.

## Deciso in realizzazione
- Dalla UI di un chatbot si cambiano modello e system prompt; tool e tipo restano nei file. Agenti della Libreria e automation di default si cambiano scrivendo l'elemento nella cartella dati (stesso nome).
- `Config.app_definitions` (variabile `APP_DEFINITIONS`) può puntare a un'altra cartella di default; vuota = `resource/definition`.

## Test e documentazione

- pytest: lettura a strati (app, cartella dati che vince per nome o per percorso, progetto); salvare un default dalla UI scrive la cartella dati e «Torna al default» lo toglie; allineamento all'avvio dei default (creati, aggiornati, quelli dell'utente intatti); origine di ogni definizione; contesto generale dall'app e dalla cartella dati.
- vitest: badge dell'origine, salvataggio di un default che diventa «tuo», «↩ Torna al default».
- Doc `definitions.md`, README (avvio senza `init-definitions.py`), `web/README.md`, regole di lavoro dei piani.
