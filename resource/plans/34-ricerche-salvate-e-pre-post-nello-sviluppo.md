# Ricerche salvate e pre/post dentro lo sviluppo

Stato: **fatto**.

## Obiettivo

1. Cercare nel codice i propri commenti (come i vecchi todoMbarePilot) con le **proprie regex**, senza doverle scrivere ogni volta, e farsi aiutare a scriverle.
2. Pre e post sviluppo non più task a parte ma **passi del task di sviluppo**.
3. In «📎 Parto da riferimenti» poter scrivere **una descrizione** prima di «✨ Proponi».

## Decisioni prese

### Ricerche salvate («regex parlanti»)
- Una ricerca salvata ha un **nome**, la regex (o il testo) e il filtro dei file, es. «Commenti MBARE».
- **Default nell'app** (`resource/definition/`, es. «TODO», «FIXME»), sovrascrivibili come le altre definizioni; **per progetto** si aggiungono in Impostazioni o con «⭐ Salva ricerca» da «🔎 Cerca nel codice».
- Si scelgono da un **menu** in «🔎 Cerca nel codice» e in **«Nuovo riferimento» da codice**: la ricerca diventa un riferimento codice (come «Salva come riferimento»).
- **«✨ Regex»**: scrivi a parole cosa cerchi, un agente piccolo con risposta strutturata propone regex, spiegazione ed esempio; la provi e la salvi con un nome.

### Pre e post dentro lo sviluppo
- Un task di sviluppo ha i passi **Pre → Delega → Piano → Esecuzione → Conferma → Post**; spariscono i tipi `pre_dev` e `post_dev`.
- Pre e Post ci sono **sempre**, ognuno con i suoi passi a parole, comandi e automation (proposti dal Pianificatore dalle regole di `sviluppo.md`), e si fanno come oggi: **«🤖 Automatico»** o **«✋ A mano»**, poi «✅ Fatto»; in più **«⏭ Salta»**.
- Un'opzione del giro in Lavora, come l'ok automatico al piano di Copilot: **«Salta da solo Pre e Post vuoti»** (senza comandi né automation).
- Il Pianificatore non propone più task pre/post: scrive Pre e Post dentro ogni sviluppo.

### Descrizione prima di «✨ Proponi»
- In «➕ Nuova attività» → «📎 Parto da riferimenti», sopra «✨ Proponi», un campo **«Cosa vuoi fare»** (testo libero, facoltativo).
- Va al Segretario (`bozza-attivita`) insieme ai titoli dei riferimenti e del contesto: è l'intenzione principale da cui proporre titolo, descrizione e voci della todo.
- «✨ Proponi» si accende anche con la sola descrizione, senza riferimenti.

## Come è fatto
- Ricerche salvate: `code-searches.yml` nelle definizioni, `Project.code_searches` per progetto, `SavedSearchService`, `GET/PUT/DELETE /code-search/saved`, `POST /code-search/regex` (agente `regex`); UI in `web/src/pages/git/SavedSearches.tsx`.
- Pre e Post: `AgentTask.pre` e `AgentTask.post` (`DevPhase`), sezioni «## Pre» e «## Post» della nota; nel piano `phases` (`<task>|pre` → fatto o saltato), `operations` per fase e `auto_skip_empty`; `POST …/plan/done`, `…/skip`, `…/auto` con `{task, phase}`.
- La conferma finale rende il task «fatto» come prima; il giro passa al task dopo quando anche il Post è fatto o saltato. Un task delegato senza passare dal Pre ha il Pre saltato.
- Il database va ricreato (colonne nuove in `project` e `activity_plan`).

## Test e documentazione
- pytest: ricerche salvate (default, progetto, sovrascrittura), agente della regex, riferimento da una ricerca salvata; passi Pre e Post dello sviluppo (automatico, a mano, salta, salto automatico dei vuoti), Pianificatore senza task pre/post; bozza dell'attività con la descrizione (anche da sola).
- vitest: menu delle ricerche, «⭐ Salva ricerca», «✨ Regex», «Nuovo riferimento» da codice; riga dello sviluppo con Pre e Post; campo «Cosa vuoi fare» e «✨ Proponi» con la sola descrizione.
- Doc `service`, `controller`, `definitions.md`, `web/README.md`; definizioni: prompt del Pianificatore, prompt di `bozza-attivita`, agente della regex, ricerche di default, contesto generale (`pre-post-sviluppo.md`).
