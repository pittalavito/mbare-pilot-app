"""The run input of «Prepara sviluppo» and «Verifica sviluppo», as text: the
app writes it, the functions read it (``FunctionContext.pipeline_input``), and
the user can type it to launch the automation by hand.

- Preparation: one line per repository, ``<repository> <branch> [<base>]``
  (``.`` = the project folder itself; with ``<base>`` the branch is created from it
  when it does not exist): ``api feature/login develop``.
- Verification: one line, ``<repository> <task> [all|touched]``:
  ``api agent-task-login.md touched``."""
from core.error import ValidationError
from models.domain.dev import PrepareTarget, TestScope

ROOT = "."


def _repository(word: str) -> str:
    return "" if word == ROOT else word.strip("/\\")


def render_prepare(targets: list[PrepareTarget]) -> str:
    return "\n".join(" ".join(part for part in (target.repository or ROOT, target.branch, target.base) if part) for target in targets)


def parse_prepare(text: str) -> list[PrepareTarget]:
    targets = []
    for line in (line.strip() for line in text.splitlines()):
        if not line:
            continue
        words = line.split()
        if len(words) not in (2, 3):
            raise ValidationError(f"Riga non valida: {line!r}. Scrivi «<repository> <branch> [<base>]» (. = la cartella del progetto).")
        targets.append(PrepareTarget(repository=_repository(words[0]), branch=words[1], base=words[2] if len(words) == 3 else ""))
    if not targets:
        raise ValidationError("Nessun repository da preparare: una riga «<repository> <branch> [<base>]» per repository.")
    return targets


def render_verify(repository: str, task: str, scope: TestScope) -> str:
    return f"{repository or ROOT} {task} {scope.value}"


def parse_verify(text: str) -> tuple[str, str, TestScope]:
    """Repository, task note and test scope (``all`` when missing)."""
    words = text.split()
    if len(words) not in (2, 3) or (len(words) == 3 and words[2] not in {scope.value for scope in TestScope}):
        raise ValidationError(f"Input non valido: {text.strip()!r}. Scrivi «<repository> <task> [all|touched]» (. = la cartella del progetto).")
    return _repository(words[0]), words[1], TestScope(words[2]) if len(words) == 3 else TestScope.ALL
