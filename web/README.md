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

- **📋 Lavoro** (`/work`, dove si apre il progetto): «📌 Oggi», nota WIP, attività, «Tutti i task», «🗄 Archivio». Un'attività si apre a step (`work/ActivityPage.tsx`):
  - **Descrivi**: titolo, descrizione, voci, riferimenti; nasce da «✍️ Scrivo io» o da «📎 Parto da riferimenti» (con «Cosa vuoi fare»).
  - **Pianifica**: «✨ Proponi i task» e task a mano; ogni sviluppo ha il suo Pre e il suo Post (passi, comandi, automation).
  - **Lavora**: il giro («▶️ Avvia», ok automatico al piano di Copilot, «Salta da solo pre e post vuoti»); per ogni task i passi e l'azione che tocca a te. Pre e Post (`work/Operation.tsx`): «🤖 Automatico», «✋ A mano» (comandi, automation, stato git, Dev, «✅ Fatto»), «⏭ Salta». Bozze Confluence e Jira: «📤 Pubblica».
  - **Chiudi**: riepilogo, «✨ Proponi cosa ho imparato», chiudi, riapri, archivia.
- **⚙️ Automation** (`/automation`): esecuzione, storico, editor del grafo, YAML.
- **🗂️ Progetto** (`/project`): note, riferimenti (anche da Jira, Confluence e «🔎 Da codice»), file, contesto, git («🔎 Cerca nel codice» con ricerche salvate e «✨ Regex»), Atlassian, impostazioni.

A destra, il **pannello dell'agente** (`project/AgentPanel.tsx`): Segretario sull'attività, Refiner su un task non delegato, Copilot su un task delegato, Architetto in Automation, Dev a richiesta. Una pagina chiede qualcosa al suo agente con `useAgentPanel().ask(testo)`. Sotto ogni risposta «🔍 Cosa ha visto il modello» (`components/TranscriptModal.tsx`). Un link `?note=` porta la nota nella sua zona (`project/noteZone.ts`).

Fuori dai progetti: **Libreria** (agenti, ruoli, prompt, tool), **Admin** (servizi, osservabilità, metriche, modelli, backup, tool, richieste di tool), **🚀 Mbare Pilot** (la bacheca, `roadmap/RoadmapPage.tsx`).

## Struttura

```
src/
  main.tsx            provider (Mantine, notifiche, modali, React Query) e router
  api/
    schema.d.ts       GENERATO da `npm run gen:api`: i tipi di ogni endpoint (non modificare)
    client.ts         `api` (client tipizzato), `unwrap` (dati o ApiError col messaggio del backend)
    <area>.ts         gli hook di un'area: projects, projectData, plan, today, wip, copilot, publish, dev, git,
                      savedSearches, context, atlassian, masking, chat, agents, catalog, automation, admin,
                      metrics, worker, toolRequests, roadmap
  app/                router, Layout (header e sezioni), stato dell'API e del worker, log, tema
  components/         FolderPicker, ModelSelect, ConfirmButton, Markdown, ToolArgsFields, TranscriptModal, agents/
  pages/
    projects/         lista dei progetti, «Apri cartella», «Crea da zero»
    project/          pagina del progetto, zone, pannello dell'agente
    work/             zona Lavoro: Oggi, attività a step, pre e post, archivio
    data/             note, WIP, attività e agent task, riferimenti, contesto, pubblicazione
    git/              commit, «🔎 Cerca nel codice», ricerche salvate
    copilot/          chat di una sessione, delega, impostazioni dei test, Dev
    chat/             conversazioni con i chatbot, dettagli del chatbot, «fanne un'automation»
    automation/       automation: esecuzione, storico, editor del grafo
    atlassian/        Jira, Confluence, preferiti
    settings/         impostazioni del progetto
    library/, admin/, roadmap/
  test/
    setup.ts          jest-dom, pulizia tra i test, matchMedia e ResizeObserver, attesa dei findBy a 3 s
    render.tsx        `mockApi` (API finta: "METODO /percorso" -> risposta) e `renderPage`
    zones.tsx         le zone come le monta il router
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
