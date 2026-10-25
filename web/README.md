# web — frontend React

Il frontend nuovo di Mbare Pilot: **React + Vite + TypeScript**, con **Mantine** per i componenti. Parla solo con l'API, come la UI Streamlit (`ui/`) che sostituirà: finché la migrazione non è completa, le due convivono.

## Avvio

```
python resource/scripts/run-web.py
```

Richiede **Node.js ≥ 22.13**. Lo script:

- avvia l'**API** (se non ne risponde già una su `API_URL`), con il ricaricamento automatico se `API_RELOAD=true`; il suo output va in `resource/logs/api.log`;
- la prima volta installa le dipendenze del frontend, poi avvia **Vite** su `WEB_PORT` (5173), che inoltra `/api/...` all'API togliendo il prefisso (niente CORS in sviluppo);
- chiuso (Ctrl+C), ferma quello che ha avviato: l'API e, con lei, il worker che l'API ha avviato.

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
  app/
    router.tsx        le rotte
    Layout.tsx        cornice: header, sezioni a sinistra
    BackendStatus.tsx stato dell'API, avvio e arresto del worker
    LogsDrawer.tsx    log di API e worker, aggiornati ogni 2 secondi
    theme.ts          tema Mantine
  pages/
    projects/         lista dei progetti, «Apri cartella» e «Crea da zero»
    project/          pagina del progetto: intestazione e tab (una rotta per tab)
  components/
    FolderPicker.tsx  selettore delle cartelle del PC tramite l'API (/folders, dentro PROJECT_ROOTS)
  test/
    setup.ts          jest-dom, pulizia tra i test, matchMedia e ResizeObserver per jsdom
    render.tsx        `mockApi` (API finta: "METODO /percorso" -> risposta) e `renderPage` (pagina con i provider e il router)
```

## Convenzioni

- **Tipi dall'API**: dopo aver cambiato un endpoint o un modello di risposta nel backend, `npm run gen:api`. Lo schema si esporta da Python senza avviare l'API (né DB né Redis), quindi segue il codice; `schema.d.ts` è nel repo, così il controllo dei tipi non dipende da Python.
- **Chiamate**: sempre `unwrap(api.GET("/percorso", { params }))` dentro `useQuery` / `useMutation`. Gli errori arrivano come `ApiError` con il messaggio del backend (status 0 = API non raggiungibile), pronti da mostrare.
- **Cache**: chiavi di query per area (`["projects"]`, `["projects", nome, "pipelines"]`...); dopo una scrittura si invalidano quelle toccate.
- **Hook per area** in `src/api/<area>.ts`: le pagine non chiamano `api` direttamente.
- **Tab di un progetto**: ognuna è una rotta figlia di `/projects/:project`, quindi si carica solo quella aperta (al contrario di `st.tabs`, che le eseguiva tutte).
- **Test**: `mockApi({...})` sostituisce `fetch` con un'API finta e `renderPage(<Pagina />, { route, path })` monta la pagina; si verifica quello che vede l'utente e cosa è stato mandato all'API.
- **Lingua**: interfaccia in italiano, codice e commenti in inglese, come nel backend.

## Migrazione

Si migra tutto insieme: Streamlit resta com'è finché React non è completo, poi `ui/` sparisce.

| Fase | Stato |
|---|---|
| 0. Base: Vite, Mantine, rotte, client generato, layout, script | ✅ |
| 1. Backend: worker gestito dall'API, script che avvia API e frontend, log | ✅ |
| 2. Progetti: lista, apertura e creazione, pagina del progetto | ✅ |
| 3. Automation: lista, esecuzione, storico, editor del grafo | |
| 4. Chat: chatbot, conversazioni, cache | |
| 5. Dati, Git, Impostazioni | |
| 6. Libreria e Admin | |
| 7. Cambio: API sotto `/api` e build servito dall'API, script, documentazione, rimozione di `ui/` | |
