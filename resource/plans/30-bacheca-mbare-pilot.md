# Bacheca di Mbare Pilot

Stato: **fatto**.

## Obiettivo

Una pagina che mostra le attività future dell'app stessa, verso la demo per datapizza. Oggi è solo da guardare: in futuro diventerà la dashboard dove chi usa l'app apre bug e attività sull'app e li affida a un agente (Claude, Copilot, agente remoto), con gli stessi strumenti dei progetti.

## Decisioni prese

### Dove
- Una voce nel menu a sinistra, **«🚀 Mbare Pilot»**, accanto a Progetti, Libreria e Admin.

### La pagina
- In cima:
  - il **traguardo «🎯 Demo datapizza»**, con quante attività mancano;
  - due righe su **cosa diventerà la dashboard** (bug e attività sull'app, da affidare a Claude, Copilot o un agente remoto).
- Una **bacheca a colonne** Da fare / In corso / Fatto, solo da guardare. Ogni card ha:
  - titolo e descrizione breve;
  - il **tipo** (uso, progettazione, refactoring, documentazione, RAG, integrazione);
  - l'**esecutore previsto** (tu, Claude, Copilot, agente remoto);
  - le **note di fattibilità** quando ci sono.

### Da dove vengono le attività
- Un file nelle definizioni, **`resource/definition/roadmap.yml`**, sovrascrivibile dalla cartella dati come le altre: si cambiano senza toccare il codice.
- Le attività di partenza:
  1. Uso quotidiano (**in corso**).
  2. Progettazione della dashboard di sviluppo.
  3. Refactoring del codice, togliendo quello superfluo.
  4. Refactoring della documentazione md.
  5. Indicizzare nel RAG la documentazione md e darla come contesto agli agenti della dashboard.
  6. Integrazione Bitbucket, Jenkins e Dynatrace come ultimi passi di un'attività (fattibilità già verificata).

## Fuori da questo piano
- Aprire bug e attività sull'app e affidarli agli agenti: si progetta dopo la demo.

## Test e documentazione

- pytest: lettura di `roadmap.yml` (app e cartella dati), validazione, API.
- vitest: voce del menu, traguardo, colonne e card.
- Doc `definitions.md`, `controller`, `web/README.md`.
