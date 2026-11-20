# Ricerche salvate e pre/post dentro lo sviluppo

Stato: **da realizzare**.

## Obiettivo

1. Cercare nel codice i propri commenti (come i vecchi todoMbarePilot) con le **proprie regex**, senza doverle scrivere ogni volta, e farsi aiutare a scriverle.
2. Pre e post sviluppo non più task a parte ma **passi del task di sviluppo**.

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

## Test e documentazione
- pytest: ricerche salvate (default, progetto, sovrascrittura), agente della regex, riferimento da una ricerca salvata; passi Pre e Post dello sviluppo (automatico, a mano, salta, salto automatico dei vuoti), Pianificatore senza task pre/post.
- vitest: menu delle ricerche, «⭐ Salva ricerca», «✨ Regex», «Nuovo riferimento» da codice; riga dello sviluppo con Pre e Post.
- Doc `service`, `controller`, `definitions.md`, `web/README.md`; definizioni: prompt del Pianificatore, agente della regex, ricerche di default, contesto generale (`pre-post-sviluppo.md`).
