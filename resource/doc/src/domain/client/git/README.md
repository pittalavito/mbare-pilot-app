# `src/domain/client/git`

Il client git: esegue l'eseguibile `git` in una cartella e traduce l'output in modelli di dominio. **Solo lettura**, tranne `pull_fast_forward` e `stash_push`: niente commit, push, checkout, merge.

```
src/domain/client/git/
  client.py     GitClient: toplevel, commit_exists, log, status
```

I modelli (`GitCommit`, `GitStatus`, `GitChange`, `GitChangeKind`) stanno in [`models/domain/git.py`](../../../models/README.md). Chi lo usa è `GitService` (`service/git_service.py`), che aggiunge le regole del progetto: trova i repository nella cartella del progetto e non esce mai da essa.

## Metodi

| Metodo | Comando git | Restituisce |
|---|---|---|
| `toplevel(cwd)` | `rev-parse --show-toplevel` | la radice del repository che contiene `cwd`, `None` se non è in un repository |
| `commit_exists(cwd, rev)` | `rev-parse --verify` | se il commit esiste |
| `log(cwd, limit, only_here, author, message, revision)` | `log` | gli ultimi `limit` commit del branch, dal più recente |
| `status(cwd, only_here)` | `status --porcelain=v2 --branch -z` | branch, upstream, ahead/behind, file modificati (anche non tracciati, esclusi gli ignorati) |
| `head(cwd)` | `rev-parse HEAD` | l'hash del commit corrente |
| `commits_between(cwd, old, new)` | `log old..new` | i commit arrivati tra due revisioni |
| `stash_push(cwd, message)` | `stash push -m` | mette da parte le modifiche ai file tracciati; `False` se non c'era niente |
| `pull_fast_forward(cwd)` | `pull --ff-only --no-rebase` | aggiorna dal remoto solo in fast-forward (timeout 120 s); le regole di sicurezza stanno in `GitService.pull_fast_forward` |

- **`only_here`**: limita il risultato a `cwd` e sottocartelle (`-- .`). Serve quando la cartella scelta è dentro un repository ma non ne è la radice.
- **Filtri del log**: `author` e `message` sono testo semplice, senza distinzione tra maiuscole e minuscole (`--fixed-strings --regexp-ignore-case`). `revision` restituisce solo quel commit.

## Come esegue git

Ogni comando gira in modo che non si blocchi mai e dia un output stabile da leggere:

- **niente pager** (`GIT_PAGER=cat`) e **niente richieste di credenziali** (`GIT_TERMINAL_PROMPT=0`);
- **niente lock opzionali** (`GIT_OPTIONAL_LOCKS=0`): leggere non blocca un git aperto in parallelo dall'utente;
- **fsmonitor spento**, output in **UTF-8**, lingua `C`;
- **timeout di 20 s**.

L'output viene letto in formati pensati per le macchine: il log con separatori invisibili (`\x1f` tra campi, `\x1e` tra commit), lo status in `porcelain=v2` separato da NUL. Così messaggi e nomi di file con spazi o caratteri strani non rompono niente.

## Errori

Tutti come `UpstreamError` (HTTP 502), con un messaggio leggibile: git non installato o non nel PATH, timeout, comando fallito (con lo stderr di git). `toplevel` e `commit_exists` invece trasformano l'errore in `None` o `False`, perché lì «non c'è» è una risposta normale.

## Test

Nei test di `GitService` (`test/unit/service/test_git_service.py`): repository veri creati in una cartella temporanea, più il parsing di `status` su output di esempio. Serve `git` nel PATH, altrimenti vengono saltati.
