# `src/function`

Le **funzioni** delle automation: codice Python che uno step esegue **senza LLM** (gratis e deterministico). Sono l'equivalente dei [tool](../tool/README.md), ma per gli step delle pipeline invece che per gli agenti.

| Funzione | Cosa fa | Parametri |
|---|---|---|
| `git_status` | branch, push/pull e file modificati di un repository del progetto, come testo; con `*` di tutti i repository: in cima il riepilogo (`N repository nel progetto: K da guardare, M a posto.` o `tutti a posto.`), poi **prima quelli da guardare** (file modificati, commit da pushare o pullare, HEAD staccato, stato non letto) e dopo gli altri, ognuno in ordine di cartella (un repository illeggibile lo dice nel testo, gli altri restano) | `repository` (vuoto = usa l'input dello step; `*` = tutti) |
| `git_fetch` | `git fetch --all --prune` di un repository o di tutti con `*`: per ognuno branch e commit da pushare/pullare dopo il fetch (un fetch fallito lo dice nel testo, gli altri restano) | `repository` (vuoto = usa l'input dello step; `*` = tutti) |
| `git_log` | ultimi commit di un repository come testo (hash, data, autore, oggetto), es. da passare a un agente che scrive le note di rilascio; gli autori sono dichiarati sensibili | `repository` (vuoto = input dello step), `limit` (1-500, default 20), `author`, `message` (vuoti = nessun filtro) |
| `git_pull_all_repo_by_branch` | porta tutti i repository del progetto su un branch e li aggiorna in fast-forward (come il tool `git_pull_all_by_branch`): un riepilogo e una riga per repository; quelli con modifiche locali o senza il branch vengono saltati. Lo step fallisce solo se falliscono tutti | `branch` (vuoto = usa l'input dello step) |
| `git_pull_repo_by_branch` | lo stesso per **un solo** repository: lo porta sul branch e lo aggiorna in fast-forward. Saltato (modifiche locali, branch che non c'è, nessun upstream) = testo con il motivo; un errore (es. remoto irraggiungibile) fa fallire lo step | `repository` (vuoto = la prima parola dell'input), `branch` (default `develop`: vale quando l'input non indica il branch). L'input dello step è `<repository> [<branch>]` (es. `api` o `api feature/login`); con `repository` nel parametro è solo `[<branch>]` |
| `maven_parent_alignment` | confronta il `pom.xml` alla radice di ogni repository (dalla cartella di lavoro) con la `version` del POM parent: il POM con `artifactId` = `parent_artifact_id` o, se vuoto, quello **riconosciuto** (il POM del progetto che i `pom.xml` alla radice nominano più spesso come `<parent>`, ma con la precedenza a uno il cui artifactId finisce con `-parent-lib`, il parent delle librerie, anche se il parent dei microservizi è nominato più volte; a parità il primo per nome). Il parent si cerca alla radice dei repository e anche nei loro **moduli** (fino a 3 cartelle, senza `target/`, `src/` e simili), per un parent tenuto in un repository multi-modulo, così una sola automation va bene per ogni progetto. Una **libreria** si controlla con la versione del suo `<parent>` (se è quel parent), un **microservizio** con le proprietà che corrispondono a `property` (un nome o un modello con `*`, es. `*.libraries.version`). In cima il riepilogo, poi «Da allineare» (valore attuale → atteso; `(non risolto)` se resta un `${...}` che il POM non definisce), «Allineati», «Non letti» (POM illeggibile) e i repository senza questi campi o senza `pom.xml`. Quando non trova il parent elenca i `<parent>` dichiarati dai POM; quando il modello non trova nessuna proprietà elenca le proprietà con «version» che ci sono davvero, per capire subito cosa cambiare. In un progetto senza nessun `pom.xml` il testo è solo `POM: nessun pom.xml nei repository del progetto.`, da usare in una condizione per non metterlo nella nota | `parent_artifact_id` (vuoto = riconosciuto), `property` (nome o modello con `*`; vuoto = solo le librerie) |
| `coverage_new_code` | la **coverage JaCoCo del codice non ancora pushato**: le righe di `src/main/java` (test esclusi) che i commit di HEAD che nessun branch remoto ha aggiungono o cambiano (dopo un merge di un branch remoto contano solo le righe che nessun commit remoto ha; niente fetch: i remoti sono quelli dell'ultimo fetch), confrontate con il `jacoco.xml` di ogni modulo. **Prima l'allineamento al parent** (JaCoCo viene dal POM parent), come `maven_parent_alignment` e con gli stessi parametri: un repository da allineare (anche con un valore `(non risolto)`) o il cui allineamento **non si può confermare** (nessun parent riconosciuto, POM senza il `<parent>` né la proprietà, POM illeggibile) viene saltato e lì **`mvn` non parte mai**. Negli altri, se il `target/jacoco.exec` di un modulo è più nuovo del suo `target/site/jacoco/jacoco.xml` (o l'XML manca), lancia `mvn -q -B jacoco:report` alla radice del repository (i test non girano; `mvnw` del repository se c'è). Un `jacoco.exec` più vecchio dell'ultimo commit dà un avviso (i test sono di prima). In cima il riepilogo, che contiene «sotto soglia» **solo** se un repository è sotto la soglia (`Coverage nuovo codice: K repository sotto soglia (80%).`, `… tutti sopra soglia (80%).`, `… niente di misurato.`), poi «Sotto soglia» (percentuale, righe coperte/totali, commit da pushare e per file le righe scoperte, es. `righe 5-6, 9`), «Sopra soglia», «Senza report» (motivo), «Saltati: non allineati al parent …», «Saltati: allineamento al parent non verificabile», «Non letti» e in una riga gli altri (niente da pushare, niente da misurare, senza `pom.xml`). Progetto senza `pom.xml`: solo `Coverage: nessun pom.xml nei repository del progetto.`; niente da pushare ovunque: solo `Coverage: nessun commit da pushare.` | `repository` (vuoto = input dello step; `*` = tutti), `threshold` (1-100, default 80), `parent_artifact_id` (vuoto = riconosciuto), `property` (nome o modello con `*`, es. `*.libraries.version`; vuoto = i microservizi vengono saltati) |
| `save_note` | salva l'input dello step come nota del progetto (tab Dati → Note) | `title` (`{date}` e `{time}` diventano data e ora; stesso nome = nota sovrascritta) |

```
src/function/
  registry.py         FUNCTION_REGISTRY (tutte le funzioni, per nome) e get_function()
  spec.py             FunctionSpec: nome, descrizione, Params, run
  context.py          FunctionContext: progetto, input della run, service
  list/
    git_status.py
    git_fetch.py
    git_log.py
    git_pull_all_repo_by_branch.py
    git_pull_repo_by_branch.py
    maven_parent_alignment.py
    coverage_new_code.py
    save_note.py
```

## Come funziona

Uno step `FUNCTION` di un'automation ha `function_name` e `params`. Quando il worker arriva a quello step, `PipelineRunner`:

1. prende la funzione con `get_function(nome)`: `ValidationError` se non esiste (più) nel codice;
2. valida i `params` con il modello `Params` della funzione;
3. chiama `run(context, step_input, params)`, che restituisce un `FunctionResult`: il suo `text` è l'output dello step e diventa l'input del successivo;
4. registra nella mappa di mascheramento del progetto i valori che il risultato dichiara sensibili (vedi sotto).

- **Parametri** (`Params`, pydantic): ogni campo ha un default e una `description`. Vengono validati **al salvataggio** dell'automation e **prima di ogni esecuzione**. L'editor degli step nella UI costruisce il form da qui (`GET /functions`): un campo `bool`, `int`, `float` o `str` diventa checkbox, numero o testo.
- **Errori**: un `AppError` sollevato dalla funzione fa fallire lo step con quel messaggio; qualsiasi altra eccezione lo fa fallire con «errore imprevisto: …».

## Valori sensibili

Una funzione non parla con un LLM, ma il suo output può finire a uno step agente successivo. Per questo dichiara i valori sensibili che legge come i tool: con campi marcati `MaskRepositoryName`, `MaskPersonName`, `MaskEmailAddress` o `MaskRepositoryNames` (da `models/domain/masking.py`) in una sottoclasse di `FunctionResult`.

```python
class Result(FunctionResult):
    repository: MaskRepositoryName   # registrato: l'agente dopo vede l'alias

def run(context, step_input, params) -> Result:
    ...
    return Result(text=testo, repository=repository)
```

Il runner li registra con `MaskingService.register_declared`; la funzione non chiama nulla. Una funzione senza valori sensibili restituisce un `FunctionResult(text=...)` semplice (come `save_note`).

## `FunctionContext`

Creato dal runner per ogni step funzione:

- `project_name`: il progetto dell'automation; le funzioni lavorano solo su quello;
- `pipeline_input`: l'input della run (l'input dello step arriva a parte, come argomento di `run`);
- i service: `git` (`GitService`), `project_data` (`ProjectDataService`) e `maven` (`MavenService`: non ha stato, è costruito da `git` con il `MavenClient` di default).

## Aggiungere una funzione

```python
# function/list/<nome>.py
from pydantic import BaseModel, Field

from function.context import FunctionContext
from function.spec import FunctionSpec


class Params(BaseModel):
    campo: str = Field("", description="Mostrato nell'editor degli step.")


def run(context: FunctionContext, step_input: str, params: Params) -> str:
    ...
    return "output dello step"


NOME = FunctionSpec(name="nome", description="Descrizione nell'editor.", params=Params, run=run)
```

Poi la spec in `FUNCTION_REGISTRY` (`registry.py`). Per una funzione senza parametri: `params=NoParams`. Se serve un service nuovo, va aggiunto a `FunctionContext` e passato da `PipelineRunner`.

## Test

`test/unit/tool/test_git_workflow.py`: `git_pull_all_repo_by_branch` (branch dall'input dello step, step fallito se falliscono tutti), `git_pull_repo_by_branch` (repository e branch dall'input o dai parametri, input sbagliati, saltato come testo ed errore che fa fallire lo step), `git_fetch` con `*`, `git_log` con gli autori dichiarati.

`test/unit/service/test_maven.py`: lettura del POM (namespace, ereditati dal parent, `${...}` risolti anche a catena, encoding, POM non valido) e `maven_parent_alignment` su repository veri: parent indicato o riconosciuto (anche con più parent candidati o nessuno, anche tenuto in un modulo), diagnostica di parent e proprietà non trovati, modello con `*` su più proprietà, progetto senza POM, librerie e microservizi allineati o no, senza POM, non pertinenti, illeggibili, senza riferimento, valori non risolti.

`test/unit/service/test_coverage.py`: lettura di `jacoco.xml`, `MavenClient` con un `mvn` finto (argomenti, `mvnw` che vince, errore con le ultime righe, timeout, `mvn` assente), righe non pushate su repository veri con un remoto (anche dopo il merge di un branch remoto), e `coverage_new_code`: `mvn` lanciato solo nei repository allineati (mai in quelli da allineare, con valori non risolti, non verificabili o senza parent), sotto e sopra soglia, report già aggiornato e `jacoco.exec` vecchio, senza report (nessun exec, `mvn` fallito, XML non scritto o rotto, file non nel report), niente da pushare o da misurare, i testi brevi.

`test/unit/service/test_function_steps.py`: ogni funzione ha descrizione e default per tutti i parametri, parametri sbagliati che nominano il campo, step non validi rifiutati al salvataggio, esecuzione dal runner (`git_status` su un repository vero che passa l'output a un agente e con `*` su tutti, anche con un repository illeggibile, con quelli da guardare prima degli altri e il riepilogo, `save_note`), errori attesi e imprevisti.
