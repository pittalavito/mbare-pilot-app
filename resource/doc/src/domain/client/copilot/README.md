# `src/domain/client/copilot`

GitHub Copilot CLI eseguito come sottoprocesso: un **turno** (`copilot -p`) per chiamata, dentro una sessione di cui l'app sceglie l'id (`--session-id`), così Copilot ricorda la conversazione da una chiamata all'altra.

```
src/domain/client/copilot/
  client.py     CopilotClient, CopilotMode: argomenti per modalità, turn(), version()
  cli.py        trovare il CLI (resolve), niente finestra di console (NO_WINDOW)
  process.py    eseguire un turno: pipe in background, timeout, annullamento, kill dell'albero
  output.py     l'output JSONL → CopilotTurn
  usage.py      il file d'uso (--usage-output-file) → CopilotUsage
```

Prerequisito: `npm install -g @github/copilot`, poi `copilot` → `/login` con l'account che ha Copilot (oppure `COPILOT_GITHUB_TOKEN`).

## Le due modalità

| Modalità | Argomenti | Cosa può fare Copilot |
|---|---|---|
| `PLAN` (preparazione) | `--mode plan` | legge il codice e risponde; il CLI stesso blocca ogni modifica fuori dalla sua cartella di sessione |
| `EXECUTE` (esecuzione) | `--mode autopilot --allow-all-tools --no-ask-user` e un `--deny-tool` per ogni voce di `denied_tools` | modifica i file e lancia comandi, tranne quelli vietati |

Sempre: `--add-dir <cartella di lavoro>` (il repository scelto, o la cartella del progetto se ne sono scelti più d'uno), `--output-format json`, `--no-color`; `--model` con il modello del turno (quello scelto per la sessione, altrimenti `COPILOT_MODEL`), se c'è.

I divieti **non sono nel codice**: li passa il servizio, dal file `global-coding-agent.yml` della cartella dei dati ([definizioni](../../../../definitions.md#coding-agent-global-coding-agentyml-coding-agentyml)). Bloccano i comandi per nome (anche dentro un comando composto), non uno script che faccia un commit da sé: per questo il servizio controlla l'HEAD prima e dopo (vedi [service](../../../service/README.md#copilot)).

## `turn(cwd, session_id, prompt, mode, timeout_seconds, denied_tools, should_cancel, model, extra_dirs)`

- Restituisce un `CopilotTurn`: l'ultimo `assistant.message` con testo, l'exit code e le richieste premium usate dalla sessione (dall'evento `result`). Non solleva per gli errori di Copilot: finiscono in `error`.
- `denied_tools` vale solo in `EXECUTE`.
- `extra_dirs`: altre cartelle che Copilot può usare, un `--add-dir` ciascuna (il servizio ci passa la cartella del task con i suoi riferimenti).
- **Uso** (`usage.py`): ogni turno passa `--usage-output-file` (in una cartella temporanea, cancellata subito dopo) e mette il contenuto in `CopilotTurn.usage`: richieste premium, crediti AI (`totalNanoAiu`, in miliardesimi), token di input (cache compresa), output, cache letta e scritta, reasoning, la somma su `modelMetrics`, più il modello usato per ultimo (`currentModel`). Sono i **totali della sessione di Copilot**, cumulativi tra un turno e l'altro (come l'`accountingSnapshot` del suo session state): la differenza la calcola il servizio. Un file che manca (Copilot fermato prima di scriverlo) o illeggibile dà `None`.
- **Timeout e annullamento** (`process.py`): ogni mezzo secondo controlla `should_cancel()` e la scadenza; se serve, chiude Copilot e tutto quello che ha avviato (`psutil`).
- **Windows** (`cli.py`): npm installa un lanciatore `.cmd`, che taglierebbe il prompt al primo a capo. Il client lo riconosce e chiama `node …/@github/copilot/npm-loader.js` direttamente. Nessuna finestra di console (`CREATE_NO_WINDOW`).
- `version()`: `copilot --version`, `None` se non è installato.

## Test

`test/fake_copilot.py` imita il CLI (stesso output JSONL, memoria dei turni per sessione, niente scritture in modalità piano). Un'esecuzione il cui task dice `FUORI` scrive anche in `../web` (un repository non scelto). Un turno di piano il cui prompt contiene `PENSACI` dorme (per l'annullamento e il timeout della preparazione). Lo usano `test/unit/service/test_copilot_service.py` e `test/unit/api/test_copilot_api.py`, su repository git veri in una cartella temporanea. La definizione di prova (`CODING_AGENT`) la scrive `test/conftest.py`. Il CLI vero non parte mai nei test, perché consuma crediti AI: la Config dei test ha `copilot_command` su un comando che non esiste, quindi un Container non trova Copilot finché un test non gli dà il finto (`test/unit/core/test_container.py` lo verifica).
