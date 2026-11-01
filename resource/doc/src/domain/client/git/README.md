# `src/domain/client/git`

Il client git: esegue l'eseguibile `git` in una cartella e traduce l'output in modelli di dominio. **Solo lettura**, tranne `pull_fast_forward`, `stash_push`, `stash_apply`, `fetch`, `switch`, `create_branch`, `add`, `commit` e `push`: mai merge, rebase, reset né push forzati.

```
src/domain/client/git/
  client.py     GitClient: i comandi della tabella sotto
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
| `stash_list(cwd)` | `stash list` | gli stash (`stash@{n}` e messaggio), dal più recente |
| `stash_apply(cwd, ref)` | `stash apply` | riapplica uno stash, che resta nella lista; `UpstreamError` se va in conflitto |
| `stash_push(cwd, message)` | `stash push -m` | mette da parte le modifiche ai file tracciati; `False` se non c'era niente |
| `pull_fast_forward(cwd)` | `pull --ff-only --no-rebase` | aggiorna dal remoto solo in fast-forward (timeout 120 s); le regole di sicurezza stanno in `GitService.pull_fast_forward` |
| `fetch(cwd)` | `fetch --all --prune` | scarica da tutti i remoti (timeout 120 s) |
| `branches(cwd)` | `for-each-ref refs/heads` | i branch locali: corrente, upstream, ahead/behind, upstream cancellato, ultimo commit |
| `remote_branches(cwd)` | `for-each-ref refs/remotes` | i branch remoti (`origin/main`), senza gli `HEAD` dei remoti |
| `remotes(cwd)` | `remote` | i nomi dei remoti |
| `is_valid_branch_name(cwd, name)` | `check-ref-format --branch` | se il nome di branch è valido |
| `switch(cwd, branch)` | `switch` | passa a un branch esistente |
| `create_branch(cwd, name, start)` | `switch -c` | crea un branch e ci passa |
| `diff_files(cwd, staged, revision, only_here)` | `diff --numstat` / `show --numstat` | file cambiati con righe aggiunte/tolte (rinomine e binari compresi) |
| `diff_patch(cwd, staged, revision, only_here)` | `diff --patch` / `show` | il patch unificato |
| `add(cwd, paths)` | `add -A --` | mette in stage file nuovi, modificati e cancellati |
| `staged_files(cwd)` | `diff --cached --name-only` | i file in stage |
| `commit(cwd, message)` | `commit -m` | committa lo stage (gli hook girano) |
| `config_value(cwd, key)` | `config --get` | un valore di configurazione, `None` se non c'è |
| `unpushed_commits(cwd, limit)` | `log HEAD --not --remotes` | i commit che nessun branch remoto ha |
| `unpushed_range(cwd)` | `rev-list --boundary HEAD --not --remotes` | quanti commit nessun branch remoto ha e i commit di confine da cui partono (nessuno = niente di HEAD è su un remoto) |
| `added_lines(cwd, base, pathspec)` | `diff -U0 base HEAD -- pathspec` | per file, le righe aggiunte o cambiate da `base` (`None` = l'albero vuoto: tutte); file cancellati esclusi |
| `commit_timestamp(cwd, revision)` | `log -1 --format=%ct` | la data del commit, in secondi |
| `push(cwd, remote, refspec, set_upstream)` | `push [-u]` | push mai forzato (timeout 120 s) |

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

Tutti come `UpstreamError` (HTTP 502), con un messaggio leggibile: git non installato o non nel PATH, timeout, comando fallito (con lo stderr di git). `toplevel`, `commit_exists`, `is_valid_branch_name` e `config_value` invece trasformano l'errore in `None` o `False`, perché lì «non c'è» è una risposta normale.

## Test

Nei test di `GitService` (`test/unit/service/test_git_service.py`, `test/unit/tool/test_git_write.py`, `test/unit/tool/test_git_workflow.py`): repository veri creati in una cartella temporanea, più il parsing di `status` su output di esempio. Serve `git` nel PATH, altrimenti vengono saltati.
