# `src/domain/client/copilot`

GitHub Copilot CLI eseguito come sottoprocesso: un **turno** (`copilot -p`) per chiamata, dentro una sessione di cui l'app sceglie l'id (`--session-id`), così Copilot ricorda la conversazione da una chiamata all'altra.

```
src/domain/client/copilot/
  client.py     CopilotClient, CopilotMode, EXECUTION_DENIED
```

Prerequisito: `npm install -g @github/copilot`, poi `copilot` → `/login` con l'account che ha Copilot (oppure `COPILOT_GITHUB_TOKEN`).

## Le due modalità

| Modalità | Argomenti | Cosa può fare Copilot |
|---|---|---|
| `PLAN` (preparazione) | `--mode plan` | legge il codice e risponde; il CLI stesso blocca ogni modifica fuori dalla sua cartella di sessione |
| `EXECUTE` (esecuzione) | `--mode autopilot --allow-all-tools --no-ask-user` e un `--deny-tool` per ogni voce di `EXECUTION_DENIED` | modifica i file e lancia comandi, ma non `git commit`, `push`, `add`, `restore`, `reset`, `checkout`, `switch`, `stash`, `rebase`, `merge`, `tag`, `branch`, `clean`… |

Sempre: `--add-dir <repository>`, `--output-format json`, `--no-color`; `--model` se `COPILOT_MODEL` è impostato.

I divieti bloccano i comandi per nome (anche dentro un comando composto), non uno script che faccia un commit da sé: per questo il servizio controlla l'HEAD prima e dopo (vedi [service](../../../service/README.md#copilot)).

## `turn(cwd, session_id, prompt, mode, timeout_seconds, should_cancel)`

- Restituisce un `CopilotTurn`: l'ultimo `assistant.message` con testo, l'exit code e le richieste premium usate dalla sessione (dall'evento `result`). Non solleva per gli errori di Copilot: finiscono in `error`.
- **Timeout e annullamento**: ogni mezzo secondo controlla `should_cancel()` e la scadenza; se serve, chiude Copilot e tutto quello che ha avviato (`psutil`).
- **Windows**: npm installa un lanciatore `.cmd`, che taglierebbe il prompt al primo a capo. Il client lo riconosce e chiama `node …/@github/copilot/npm-loader.js` direttamente. Nessuna finestra di console (`CREATE_NO_WINDOW`).
- `version()`: `copilot --version`, `None` se non è installato.

## Test

`test/fake_copilot.py` imita il CLI (stesso output JSONL, memoria dei turni per sessione, niente scritture in modalità piano). Lo usano `test/unit/service/test_copilot_service.py` e `test/unit/api/test_copilot_api.py`, su repository git veri in una cartella temporanea.
