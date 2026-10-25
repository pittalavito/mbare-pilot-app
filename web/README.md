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

## Struttura

```
src/
  main.tsx            provider (Mantine, notifiche, modali, React Query) e router
  api/
    schema.d.ts       GENERATO da `npm run gen:api`: i tipi di ogni endpoint (non modificare)
    client.ts         `api` (client tipizzato), `unwrap` (dati o ApiError col messaggio del backend)
    projects.ts       hook dei progetti e delle cartelle (useProjects, useProject, useOpenFolder, ...)
    automation.ts     hook delle automation e delle esecuzioni (con polling)
    chat.ts           hook di chatbot, conversazioni, messaggi e cache (route)
    catalog.ts        cataloghi condivisi dagli editor: modelli, tool, funzioni, agenti
    projectData.ts    note e file del progetto (upload col contenuto grezzo, download da link)
    git.ts            repository, log e stato (mutation: git gira solo sui pulsanti)
    atlassian.ts      impostazioni del sito, issue Jira, pagine Confluence, preferiti
    masking.ts        valori mascherati e sincronizzazione delle definizioni YAML
    agents.ts         agenti, ruoli e versioni dei prompt, per scope (Libreria o progetto)
    admin.ts          config, observability (run, tool call, trace), catalogo modelli, backup del DB
  app/
    router.tsx        le rotte
    Layout.tsx        cornice: header, sezioni a sinistra
    BackendStatus.tsx stato dell'API, avvio e arresto del worker
    LogsDrawer.tsx    log di API e worker, aggiornati ogni 2 secondi
    theme.ts          tema Mantine
  pages/
    projects/         lista dei progetti, «Apri cartella» e «Crea da zero»
    project/          pagina del progetto: intestazione e tab (una rotta per tab)
    data/             tab Dati: note markdown (modifica/anteprima, Ctrl+S) e file
    git/              tab Git: commit con filtri e file modificati
    atlassian/        tab Atlassian: Jira, Confluence, preferiti
    library/          pagina Libreria: agenti globali (la stessa sezione Agenti) e catalogo dei tool
    admin/            pagina Admin: servizi, observability, modelli, backup (tab in ?tab=)
    settings/         tab Impostazioni: generale, Atlassian, mascheramento, definizioni, agenti, rimozione
    chat/             tab Chat: conversazioni, messaggi in markdown, «Metti in cache», modale del chatbot
    automation/       tab Automation (esecuzione e storico), editor del grafo (React Flow) e graphDraft (la bozza, funzioni pure)
  format.ts           dimensioni dei file e date nel formato italiano
  components/
    FolderPicker.tsx  selettore delle cartelle del PC tramite l'API (/folders, dentro PROJECT_ROOTS)
    ModelSelect.tsx   scelta del modello di un agente, segnalando quelli senza chiave del provider
    ConfirmButton.tsx pulsante rosso con conferma in un popover, per le azioni irreversibili
    Markdown.tsx      markdown con la tipografia dell'app
    agents/           sezione Agenti (agenti, prompt, ruoli) per scope: Impostazioni del progetto e Libreria
  test/
    setup.ts          jest-dom, pulizia tra i test, matchMedia e ResizeObserver per jsdom
    render.tsx        `mockApi` (API finta: "METODO /percorso" -> risposta) e `renderPage` (pagina con i provider e il router)
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
