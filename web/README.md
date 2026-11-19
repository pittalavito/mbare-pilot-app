# web — frontend React

Il frontend di Mbare Pilot: **React + Vite + TypeScript**, con **Mantine** per i componenti. Parla solo con l'API, sotto `/api`.

## Avvio

Richiede **Node.js ≥ 22.13**. Due modi:

```
python resource/scripts/run-app.py
```

**Uso normale**, una sola porta: compila il frontend in `dist/` se manca o se un sorgente è più recente, poi avvia l'API (se non ne risponde già una su `API_URL`), che serve l'app in `/` e sé stessa in `/api`.

```
python resource/scripts/run-web.py
```

**Sviluppo**, con la ricarica istantanea: avvia l'API come sopra e **Vite** su `WEB_PORT` (5173), che inoltra `/api/...` all'API (niente CORS). Apri `http://localhost:5173`.

In entrambi i casi:

- l'output dell'API va in `resource/logs/api.log`; con `API_RELOAD=true` l'API si riavvia da sola quando cambia `src/`;
- la prima volta si installano le dipendenze del frontend;
- chiuso lo script (Ctrl+C), si ferma quello che ha avviato: l'API e, con lei, il worker che l'API ha avviato.

Il **worker** si avvia e si ferma dall'intestazione della pagina (lo gestisce l'API); accanto, il pulsante dei **log** di API e worker.

| Comando (in `web/`) | Cosa fa |
|---|---|
| `npm run dev` | server di sviluppo con ricaricamento istantaneo |
| `npm run build` | controllo dei tipi + build in `dist/` |
| `npm test` | test (Vitest + Testing Library) |
| `npm run typecheck` | solo il controllo dei tipi |
| `npm run gen:api` | rigenera `src/api/schema.d.ts` dall'OpenAPI dell'API |

## Stack

| Cosa | Libreria |
|---|---|
| Build e server di sviluppo | Vite 8 |
| Componenti, tema (chiaro/scuro), form, modali, notifiche | Mantine 7 |
| Navigazione: una URL per pagina | React Router 7 |
| Dati dall'API: cache, aggiornamento dopo le scritture, polling | TanStack Query 5 |
| Client tipizzato | `openapi-fetch` con i tipi di `openapi-typescript` |
| Editor del grafo delle automation | React Flow (`@xyflow/react`) |
| Icone | Tabler Icons |

## Zone del progetto

Un progetto ha tre zone (piano 13): **📋 Lavoro** (`/work`, dove si apre: WIP, attività e i loro task, «Tutti i task», con «📌 Oggi» in cima; la scheda aperta di default resta Attività), **⚙️ Automation** (`/automation`) e **🗂️ Progetto** (`/project`: note, riferimenti, file, contesto, git, Atlassian, impostazioni). In Lavoro e Automation, a destra, il **pannello dell'agente** (`project/AgentPanel.tsx`): Segretario sull'attività (una conversazione per attività), Refiner su un task non delegato, Copilot su un task delegato, Architetto in Automation; il menu cambia agente a mano (anche i chatbot personalizzati) finché non apri altro; si nasconde (ricordato nel browser) ed è un cassetto sugli schermi stretti. Una pagina chiede qualcosa al suo agente con `useAgentPanel().ask(testo)`. **L'Operatore** (piano 11) si sceglie dal menu, o arriva da «Fallo fare all'Operatore» nella delega (`ask(testo, "operator")`, che mostra anche il pannello nascosto): sopra la sua chat i comandi che chiede di lanciare («Sempre», «Solo stavolta», «No»), sotto ogni risposta con una run «✅ Giusto: fanne un'automation» (`chat/LearnModal.tsx`: azioni da tenere, campi da correggere, salva). **Le attività** (piano 18): «➕ Nuova attività» apre una finestra con due strade (`data/NewActivityModal.tsx`): «✍️ Scrivo io» (titolo e descrizione) e «📎 Parto da riferimenti» (`data/ActivityFromReferences.tsx`: riferimenti, Jira, Confluence, contesto; l'agente propone titolo, descrizione e voci). Un'attività si apre **a step** (`work/ActivityPage.tsx`): barra in cima 1. Descrivi → 2. Pianifica → 3. Lavora → 4. Chiudi (lo step in `?step=`, altrimenti da dove è l'attività; «Avanti» in fondo), stato in testata che segue gli step. **Descrivi**: titolo, descrizione, voci, riferimenti (il Segretario in chat). **Pianifica**: «✨ Proponi i task» (o «Proponi altri task») e «➕ Task» a mano, righe compatte (dettagli a richiesta, ▲▼, ✕), «Crea N task» (nascono da fare), «Scarta le proposte». **Lavora**: avviso «Il worker è fermo» con «Avvia il worker», «▶️ Avvia»/«⏸ Pausa», l'ok automatico al piano di Copilot (niente più opzioni prima e dopo Copilot, piano 22); ogni task è una riga con i passi, **«Apri»** (la scheda del task, con `?from=` l'attività: in cima alla scheda «← Torna all'attività» riporta qui con il task selezionato) e il pulsante di quello che tocca a te (delega a mano, rispondi o leggi la risposta, rimanda a Copilot, riprova la delega, «✅ Controlla e conferma»); un task **pre o post sviluppo** non va a Copilot (piano 25, `work/Operation.tsx`): «🤖 Automatico» lancia senza agente i suoi comandi e poi la sua automation (prima chiede l'ok ai comandi non permessi: «Sempre», «Solo stavolta», «No»; l'esito sotto la riga), o, se non ne ha, apre Dev con la richiesta pronta (`work/devRequest.ts`); «✋ A mano» apre la dashboard sotto la riga: i comandi uno per uno (modificabili, «▶️» e output), l'automation da lanciare, «🌿 Stato git», «💬 Dev in chat» e «✅ Fatto». Cliccando la riga (`?task=`) il pannello a destra mostra la chat di Copilot di quel task. In **Pianifica** i task pre e post sviluppo hanno anche i **passi**, i **comandi** (uno per riga) e l'**automation**. **Chiudi**: riepilogo, «✨ Proponi cosa ho imparato» (un punto per riga, «Tema: testo»), «✅ Chiudi attività» (avvisa se resta qualcosa aperto; ogni punto va in cima al suo tema in `context/imparato.md`, piano 27), «↩ Riapri». In «📌 Oggi», «Chiudi →» apre l'attività allo step Chiudi. Nella **finestra di delega** un task senza codice (analisi, Confluence, Jira) parte da «Nessun repository» (Copilot lavora nei dati del progetto), a meno che il piano non ne proponga uno; nella chat di una sessione mai eseguita «🔀 Cambia repository» (piano 21: la chat resta, il task si sposta). Niente preparazione nella delega (piano 22: è un task pre sviluppo). Nella **scheda del task** un pre o post sviluppo ha i «Passi suggeriti», i «Comandi» e l'«Automation»; i test di `run_tests` si scelgono sul post sviluppo. In **Progetto → Contesto** «📐 Regole di sviluppo (modello)» crea `sviluppo.md`, le regole che il Pianificatore segue per i task pre e post sviluppo; «📏 Convenzioni», «📖 Glossario», «🧭 Decisioni» (modello) creano gli altri documenti pronti e «🗺 Genera mappa dei repository» scrive `repository.md` (piano 27); sotto, «Generale (da definizioni)» mostra in sola lettura il contesto generale per gli agenti (piano 26), e la ricerca di prova dice per ogni pezzo se viene dal progetto o dal generale. Un'automation con campi li chiede quando la esegui. Nell'editor «➕ Tool (codice)»: scegli il tool e compili gli argomenti nel form (`components/ToolArgsFields.tsx`, lo stesso di **Admin → Tool**, dove un tool si prova da solo su un progetto: `admin/ToolTrial.tsx`). Un link `?note=` porta alla zona della nota: attività, agent task e WIP in Lavoro, il resto in Progetto (`project/noteZone.ts`; gli agenti scrivono i link già così, anche quello della chat di Copilot, che apre il suo task). Niente reindirizzamenti dei link di prima (piano 17).

## Struttura

```
src/
  main.tsx            provider (Mantine, notifiche, modali, React Query) e router
  api/
    schema.d.ts       GENERATO da `npm run gen:api`: i tipi di ogni endpoint (non modificare)
    client.ts         `api` (client tipizzato), `unwrap` (dati o ApiError col messaggio del backend)
    projects.ts       hook dei progetti e delle cartelle (useProjects, useProject, useOpenFolder, ...)
    automation.ts     hook delle automation e delle esecuzioni (con polling)
    chat.ts           hook di chatbot (solo lettura), conversazioni, messaggi e cache delle automation
    catalog.ts        cataloghi condivisi dagli editor: modelli, tool (e i loro argomenti, la prova da Admin), agenti
    projectData.ts    note (anche agent task e attività), file del progetto (upload col contenuto grezzo, download da link)
    git.ts            repository, log e stato (mutation: git gira solo sui pulsanti)
    atlassian.ts      impostazioni del sito, issue Jira, pagine Confluence, preferiti
    masking.ts        valori mascherati e sincronizzazione delle definizioni YAML
    agents.ts         agenti, ruoli e versioni dei prompt, per scope (Libreria o progetto)
    admin.ts          config, observability (run, tool call, trace), catalogo modelli, backup del DB
    copilot.ts        sessioni Copilot, chat, ok e annullamento, uso per sessione e per Observability
    copilot.ts        sessioni Copilot: delega, chat di preparazione, ok, annullamento (polling durante l'esecuzione)
  app/
    router.tsx        le rotte
    Layout.tsx        cornice: header, sezioni a sinistra
    BackendStatus.tsx stato dell'API, avvio e arresto del worker
    LogsDrawer.tsx    log di API e worker, aggiornati ogni 2 secondi
    theme.ts          tema Mantine
  pages/
    projects/         lista dei progetti, «Apri cartella» e «Crea da zero»
    project/          pagina del progetto: intestazione, zone (una rotta per zona) e pannello dell'agente (AgentPanel); ProjectZone = zona «Progetto» (note, riferimenti, file, contesto, git, Atlassian, impostazioni; sezione in ?tab=); noteZone.ts = in che zona sta una nota
    work/             zona «Lavoro», dove si apre il progetto: «📌 Oggi», WIP, attività a step (ActivityPage: Descrivi, Pianifica, Lavora, Chiudi; un agent task nato da un'attività si apre dentro di lei, con «← attività»), «Tutti i task»; ?note= dice cosa è aperto
    data/             i pezzi di Lavoro e Progetto: note markdown (modifica/anteprima, Ctrl+S), WIP, attività e agent task (form dei template, con i riferimenti collegati: ReferencesSection), riferimenti, file; DataSettings sceglie cosa mostra la zona Progetto
    git/              sezione Git di Progetto: commit con filtri e file modificati; «🔎 Cerca nel codice» (CodeSearch: testo o regex, filtri file e repository, risultati per file, «Salva come riferimento» con «Collega a un task»)
    atlassian/        sezione Atlassian di Progetto: Jira, Confluence, preferiti; «📎 Crea riferimento» copia issue e pagine nei riferimenti (CopyToReference)
    library/          pagina Libreria: agenti globali (la stessa sezione Agenti) e catalogo dei tool
    admin/            pagina Admin: servizi (con «🤖 Tool di Copilot»: i tool dell'app e quelli vietati nell'esecuzione), observability (agent run, tool call, Copilot), modelli, backup, tool, richieste di tool (ToolRequests: le richieste dell'Architetto per Claude Code, il token e il comando per collegarlo, «Scarta»; tab in ?tab=)
    settings/         sezione Impostazioni di Progetto: generale, Atlassian, mascheramento, definizioni, agenti, rimozione
    copilot/          Copilot: SessionView (la chat di una sessione: domande, «Ok, parti», esecuzione dal vivo, file cambiati, nel pannello del task delegato), modale «Delega a Copilot» (dal form del task, senza preparazione), DevSettingsModal (Progetto → Impostazioni)
    chat/             ConversationView (la conversazione con un chatbot: messaggi in markdown, proposte dell'Architetto, «Metti in cache» se il chatbot ha la cache), ChatbotDetails (dove si cambia solo il modello), AutomationProposal
    automation/       tab Automation (esecuzione e storico), editor del grafo (React Flow) e graphDraft (la bozza, funzioni pure)
  format.ts           dimensioni dei file e date nel formato italiano
  components/
    FolderPicker.tsx  selettore delle cartelle del PC tramite l'API (/folders, dentro PROJECT_ROOTS)
    ModelSelect.tsx   scelta del modello di un agente, segnalando quelli senza chiave del provider
    ConfirmButton.tsx pulsante rosso con conferma in un popover, per le azioni irreversibili
    Markdown.tsx      markdown con la tipografia dell'app
    agents/           sezione Agenti (agenti, prompt, ruoli) per scope: Impostazioni del progetto e Libreria; nella finestra dell'agente anche la «Risposta strutturata» (output: wip, plan, draft)
  test/
    setup.ts          jest-dom, pulizia tra i test, matchMedia e ResizeObserver per jsdom
    render.tsx        `mockApi` (API finta: "METODO /percorso" -> risposta) e `renderPage` (pagina con i provider e il router)
    zones.tsx         `zoneRoutes()`: le zone Lavoro e Progetto e i link di prima, come le monta il router
```

## Convenzioni

- **Tipi dall'API**: dopo aver cambiato un endpoint o un modello di risposta nel backend, `npm run gen:api`. Lo schema si esporta da Python senza avviare l'API (né DB né Redis), quindi segue il codice; `schema.d.ts` è nel repo, così il controllo dei tipi non dipende da Python.
- **Chiamate**: sempre `unwrap(api.GET("/percorso", { params }))` dentro `useQuery` / `useMutation`. Gli errori arrivano come `ApiError` con il messaggio del backend (status 0 = API non raggiungibile), pronti da mostrare.
- **Cache**: chiavi di query per area (`["projects"]`, `["projects", nome, "pipelines"]`...); dopo una scrittura si invalidano quelle toccate.
- **Hook per area** in `src/api/<area>.ts`: le pagine non chiamano `api` direttamente.
- **Tab di un progetto**: ognuna è una rotta figlia di `/projects/:project`, quindi si carica solo quella aperta (non tutte insieme).
- **Pagine pesanti in lazy**: l'editor del grafo (React Flow) è una rotta `lazy`, scaricata solo quando si apre; le librerie (Mantine, React) sono in chunk separati (`codeSplitting` in `vite.config.ts`).
- **Test**: `mockApi({...})` sostituisce `fetch` con un'API finta e `renderPage(<Pagina />, { route, path })` monta la pagina; si verifica quello che vede l'utente e cosa è stato mandato all'API.
- **Lingua**: interfaccia in italiano, codice e commenti in inglese, come nel backend.
