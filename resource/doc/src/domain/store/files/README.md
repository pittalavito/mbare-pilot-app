# `src/domain/store/files`

Lo store dei file su disco locale: salva, legge, elenca e cancella file sotto **una sola cartella radice**, senza mai uscirne. Lì l'app tiene i dati dei progetti (note e file caricati).

```
src/domain/store/files/
  repository.py        FileStore: la radice e la risoluzione sicura dei percorsi
  file_repository.py   LocalFileRepository: list, get, read, save, delete
  store.py             punto unico di import (LocalFileRepository, StoredFile)
```

La radice è `Config.projects_data_root`, cioè `<MBARE_PILOT_HOME>/projects` (default `~/.mbare-pilot/projects`). Chi lo usa è `StoreService`; i percorsi dentro la radice li decide [`domain/project/data_paths`](../../project/README.md) (`<slug>/notes/…`, `<slug>/files/…`).

## Indirizzare un file: `file_id`

Ogni file si indica con un `file_id`: il percorso **relativo alla radice**, con `/` (es. `my-app/notes/setup.md`). Chi chiama non vede mai percorsi assoluti.

`FileStore._safe_path()` lo trasforma in percorso assoluto e controlla che resti dentro la radice: `..`, percorsi assoluti o `\` che portano fuori vengono rifiutati con un `ValidationError`.

## Metodi (`LocalFileRepository`)

| Metodo | Cosa fa |
|---|---|
| `list(prefix="")` | tutti i file sotto `prefix` (o tutta la radice), in ordine; esclude i `.gitkeep` |
| `get(file_id)` | lo `StoredFile`, `None` se non esiste |
| `read(file_id)` | i byte del file; `NotFoundError` se non esiste |
| `save(file_id, data)` | scrive o sovrascrive, creando le cartelle che mancano |
| `delete(file_id)` | `True` se ha cancellato un file, `False` se non c'era |

`StoredFile` (`models/store/files.py`) ha `file_id`, `size` e `mtime_ns`.

## Perché niente Adapter/Factory

Gli store su Postgres e Redis convertono i loro record in modelli di dominio. Qui non serve: `StoredFile` è già la forma che usa il resto dell'app, e il repository lo costruisce direttamente.

## Test

`test/unit/domain/store/files/test_file_repository.py`: salvataggio, lettura, elenco e cancellazione; file mancante; percorsi che provano a uscire dalla radice. Usano la fixture `files_repository` di `test/conftest.py` (in arrivo), con la radice in una cartella temporanea.
