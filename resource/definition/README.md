# Definizioni di default

Le definizioni dell'app, versionate con il codice (piano 28): l'app le legge da qui. All'avvio allinea da sola agenti, chatbot e automation a questi file (e a quelli della cartella dati).

**Cambiarle senza toccare l'app**: in `<MBARE_PILOT_HOME>/definition/` metti solo quello che cambi.
- Nei file YAML globali (`global-agent.yml`, `global-chat-bots.yml`, `global-automation.yml`) un elemento con lo **stesso nome** vince su quello di qui; gli altri restano questi (il tuo `global-chat-bots.yml` può contenere solo il Refiner cambiato).
- Negli altri file (`global-coding-agent.yml`, `coding-agent/*.md`, `context/*.md`) vince il file con lo **stesso percorso**.
- Dalla UI di un chatbot, «Salva prompt» o il cambio di modello scrivono il chatbot lì (diventa «tuo»); «↩ Torna al default» lo toglie.
- I file dei progetti (`project/<slug>/`) stanno solo lì.

| File | Cosa |
|---|---|
| `roadmap.yml` | la bacheca «🚀 Mbare Pilot»: le modifiche future dell'app (dalla UI si scrive la copia nella cartella dati) |
| `code-searches.yml` | le ricerche salvate nel codice di ogni progetto (piano 34): TODO, FIXME, Commenti Mbare Pilot |
| `global-coding-agent.yml` | prompt, divieti e modelli (con i prezzi) di Copilot: **senza questo Copilot non parte** |
| `coding-agent/bugfix.md` | un prompt di preparazione da scegliere quando deleghi un bug |
| `coding-agent/analisi.md` | il prompt dei task di tipo analisi (`type_prompts`): Copilot legge e risponde, senza cambiare il codice |
| `global-agent.yml` | gli agenti della Libreria: l'esempio `hello` e quelli che l'app chiama da sola con risposta strutturata (`wip`, `pianificatore`, `bozza-attivita`, `imparato`, `regex`) |
| `global-chat-bots.yml` | i chatbot di ogni progetto (salvo stesso nome nel progetto): qui quello delle automation |
| `global-automation.yml` | «Prova git»: stato git di tutti i repository salvato in una nota, poi stop (le altre si rifanno poco alla volta) |
| `context/*.md` | Il contesto generale per gli agenti (piano 26): come funziona l'app, un file per tema; si cerca con `search_context` in ogni progetto |

Le definizioni dei singoli progetti (`project/<slug>/`) non stanno qui: sono tue e dei tuoi progetti. Formato e regole: [definitions.md](../doc/definitions.md). Un test (`test/unit/test_definition_examples.py`) verifica che questi file restino validi.
