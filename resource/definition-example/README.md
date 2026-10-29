# Definizioni di esempio

Un punto di partenza per la cartella `definition/` dei dati (`MBARE_PILOT_HOME`): da copiare, non da usare da qui. L'app legge solo `<MBARE_PILOT_HOME>/definition/`.

```bash
python resource/scripts/init-definitions.py
```

Lo script copia in `<MBARE_PILOT_HOME>/definition/` i file che mancano e non sovrascrive mai quelli che ci sono già.

| File | Cosa |
|---|---|
| `global-coding-agent.yml` | prompt, divieti e modelli (con i prezzi) di Copilot: **senza questo Copilot non parte** |
| `coding-agent/bugfix.md` | un prompt di preparazione da scegliere quando deleghi un bug |
| `global-agent.yml` | l'agente di esempio `hello` della Libreria |
| `global-chat-bots.yml` | i chatbot di ogni progetto (salvo stesso nome nel progetto): qui quello delle automation |
| `global-automation.yml` | «Stato del mattino»: stato git di tutti i repository, riassunto in una nota |

Le definizioni dei singoli progetti (`project/<slug>/`) non stanno qui: sono tue e dei tuoi progetti. Formato e regole: [definitions.md](../doc/definitions.md). Un test (`test/unit/test_definition_examples.py`) verifica che questi file restino validi.
