# web — frontend React

Il frontend nuovo di Mbare Pilot: **React + Vite + TypeScript**, con **Mantine** per i componenti. Parla solo con l'API, come la UI Streamlit (`ui/`) che sostituirà: finché la migrazione non è completa, le due convivono.

## Avvio

```
python resource/scripts/run-web.py      # installa le dipendenze la prima volta, poi avvia Vite su WEB_PORT (5173)
```

L'API va avviata come prima (pannello Backend di Streamlit). Vite inoltra `/api/...` all'API di `API_URL` (dal `.env`), togliendo il prefisso: niente CORS in sviluppo.

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
| Componenti, tema (chiaro/scuro), form, modali, notifiche | Mantine 7 |
| Navigazione: una URL per pagina | React Router 6 |
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
  app/
    router.tsx        le rotte
    Layout.tsx        cornice: header con lo stato dell'API, sezioni a sinistra
    theme.ts          tema Mantine
  pages/              una pagina per sezione
  components/         componenti condivisi
  test/setup.ts       jest-dom, matchMedia e ResizeObserver per jsdom
```

## Convenzioni

- **Tipi dall'API**: dopo aver cambiato un endpoint o un modello di risposta nel backend, `npm run gen:api`. Lo schema si esporta da Python senza avviare l'API (né DB né Redis), quindi segue il codice; `schema.d.ts` è nel repo, così il controllo dei tipi non dipende da Python.
- **Chiamate**: sempre `unwrap(api.GET("/percorso", { params }))` dentro `useQuery` / `useMutation`. Gli errori arrivano come `ApiError` con il messaggio del backend (status 0 = API non raggiungibile), pronti da mostrare.
- **Cache**: chiavi di query per area (`["projects"]`, `["projects", nome, "pipelines"]`...); dopo una scrittura si invalidano quelle toccate.
- **Lingua**: interfaccia in italiano, codice e commenti in inglese, come nel backend.

## Migrazione

Si migra tutto insieme: Streamlit resta com'è finché React non è completo, poi `ui/` sparisce.

| Fase | Stato |
|---|---|
| 0. Base: Vite, Mantine, rotte, client generato, layout, script | ✅ |
| 1. Backend: worker gestito dall'API, build servito dall'API | |
| 2. Progetti: lista, apertura e creazione, pagina del progetto | |
| 3. Automation: lista, esecuzione, storico, editor del grafo | |
| 4. Chat: chatbot, conversazioni, cache | |
| 5. Dati, Git, Impostazioni | |
| 6. Libreria e Admin | |
| 7. Cambio: script, documentazione, rimozione di `ui/` | |
