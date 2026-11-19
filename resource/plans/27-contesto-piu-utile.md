# Contesto più utile agli agenti

Stato: **fatto**.

## Obiettivo

Dare agli agenti il contesto che oggi manca: documenti del progetto pronti da compilare, la mappa dei repository generata, più esempi e regole nel contesto generale, quello che le attività insegnano ordinato per tema, l'elenco dei documenti nel prompt e una misura di quanto la ricerca trova il pezzo giusto.

## Decisioni prese

### Modelli pronti in Progetto → Contesto
- Oltre a `sviluppo.md`: **`convenzioni.md`** (branch, commit, package, stile, test), **`glossario.md`** (termini del dominio), **`decisioni.md`** (scelte architetturali con il perché). Un pulsante per ognuno che manca, come «📐 Regole di sviluppo (modello)».

### `repository.md`: la mappa dei repository
- **«🗺 Genera mappa dei repository»** la scrive dai file, senza LLM. Per ogni repository:
  - linguaggio e build (Maven, npm, Python…; comando di build e di test rilevato);
  - chi dipende da chi (le librerie del progetto usate dai servizi, quindi l'ordine librerie → servizi);
  - branch corrente e branch principali.
- **Rigenerarla riscrive solo la parte automatica** (tra due segni); le note scritte a mano fuori da quella parte restano.
- Si indicizza come gli altri documenti: il Pianificatore e Dev la trovano con `search_context`.

### Contesto generale (definizioni `context/`)
- **Esempi di task ben fatti**, uno per tipo (sviluppo, analisi, Confluence, Jira, pre e post sviluppo), con obiettivo, criteri e vincoli.
- **Errori comuni e cosa fare**: comando non permesso, delega fallita, worker fermo, indice vuoto, Copilot fermo.
- **Cosa non fare**: le regole di sicurezza in un posto solo.
- **Esempi di automation** per l'Architetto: automation fatte bene e quando conviene un'automation rispetto a un comando.

### `imparato.md` per tema
- Alla chiusura dell'attività l'agente `imparato` propone per ogni punto un **tema** (es. «Build», «Test», «Dominio»); l'utente lo corregge. Ogni punto va sotto il suo `## tema` (creato se manca), con data e attività: pezzi più facili da trovare.

### Elenco dei documenti nel prompt
- In fondo al system prompt degli agenti con `search_context` l'app aggiunge l'elenco dei titoli dei documenti (progetto e generale), così sanno cosa cercare. Poche righe; Copilot no.

### Misura della ricerca
- Nelle **Metriche**: un set di domande tipiche per agente sul contesto generale (es. «come si avvia il giro?», «cosa faccio se un comando non è permesso?»), con hit@5 nella valutazione RAG che c'è già.

## Deciso in realizzazione
- I punti di `imparato.md` si scrivono una per riga come «Tema: testo» (senza tema vanno sotto «Generale»); i temi uguali a meno delle maiuscole finiscono nella stessa sezione.
- La mappa dei repository riconosce Maven (artifactId e parent), npm (`package.json`) e Python (`pyproject.toml`); i branch principali sono `main`, `master`, `develop`.
- Le domande sul contesto generale sono in `resource/eval/rag/general-questions.json` dell'app e usano i documenti di esempio.

## Test e documentazione

- pytest: modelli; mappa generata (linguaggio, build, dipendenze, branch; note a mano conservate alla rigenerazione); `imparato.md` per tema; elenco dei documenti nel prompt (non per Copilot); set di domande della valutazione.
- vitest: pulsanti dei modelli e «Genera mappa»; tema dei punti alla chiusura.
- Doc `service`, `controller`, `definitions.md`, `web/README.md`; definizioni: nuovi documenti in `context/`, prompt dell'agente `imparato` e schema della risposta (definizioni e copia dell'app).
