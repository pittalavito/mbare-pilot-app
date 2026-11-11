"""run_tests function («Verifica sviluppo»): the tests of the repository
Copilot worked on, all of them or only the ones its changes touched
(domain/dev/tests.py). The run input is ``<repository> <task> [all|touched]``
(domain/dev/inputs.py).

The command is the repository's one in the project's settings, or the one
detected from its files (``mvn -B test``, ``uv run pytest``, ``npm test``). A
repository whose tool is not recognised and has no command, or «touched»
with no test touched, is said in the text and is not a failure. Failing tests
fail the step, with the lines that say what failed (read by the code, no LLM):
the user decides whether to send them back to Copilot."""
from pydantic import BaseModel, Field

from core.error import ConflictError, ValidationError
from domain.dev import tests
from domain.dev.inputs import ROOT, parse_verify
from domain.project import task_folder
from function.context import FunctionContext
from function.spec import FunctionResult, FunctionSpec
from models.domain.dev import TestKind, TestScope
from models.domain.git import GitChangeKind
from models.domain.masking import MaskRepositoryName


class Params(BaseModel):
    timeout_minutes: int = Field(20, ge=1, le=240, description="Dopo quanti minuti i test si fermano (e lo step fallisce).")


class Result(FunctionResult):
    repository: MaskRepositoryName


def run(context: FunctionContext, step_input: str, params: Params) -> Result:
    repository, _, scope = parse_verify(context.pipeline_input)
    name = repository or ROOT
    root = context.git.repository_folder(context.project_name, repository)
    root_files = {path.name for path in root.iterdir()}
    kind = tests.detect(root_files)
    base = context.project_data.test_command(context.project_name, repository) or tests.default_command(kind, root_files)
    if not base:
        return Result(text=f"Test: {name} non ha un comando dei test e non lo riconosco: scrivilo nelle impostazioni del progetto.",
                      repository=name)
    selectors: list[str] = []
    if scope is TestScope.TOUCHED:
        changed = [change.path for change in context.git.status(context.project_name, repository).changes
                   if change.kind is not GitChangeKind.DELETED and not task_folder.is_task_path(change.path)]
        selectors = tests.touched_tests(kind, changed, context.git.files(context.project_name, repository))
        if not selectors:
            return Result(text="Test: nessun test toccato dalle modifiche, non lanciati.", repository=name)
    try:
        arguments = tests.command(base, kind, selectors)
    except ValueError as exc:
        raise ValidationError(f"Comando dei test non valido ({base!r}): {exc}") from exc
    shown = " ".join(arguments)
    result = context.commands.run(root, arguments, params.timeout_minutes * 60)
    which = f"solo toccati ({len(selectors)})" if selectors else "tutti"
    if result.returncode != 0:
        raise ConflictError(f"Test falliti ({which}, `{shown}`):\n" + "\n".join(tests.failures(kind, result.output)))
    last = next((line.strip() for line in reversed(result.output.splitlines()) if line.strip()), "")
    return Result(text=f"Test {which}: ok (`{shown}`)" + (f"\n{last}" if last and kind is not TestKind.UNKNOWN else ""), repository=name)


RUN_TESTS = FunctionSpec(
    name="run_tests",
    description="Lancia i test del repository (tutti o solo quelli toccati); input «<repository> <task> [all|touched]» (senza LLM).",
    params=Params,
    run=run,
)
