"""Function registry: the Python functions pipeline steps can run, keyed by name.

A function file under function/list/ declares its ``Params`` (pydantic), a
``run(context, step_input, params) -> str`` and its ``FunctionSpec``; add the
spec here to make it selectable in the step editor.
"""
from core.error import ValidationError
from function.list.clean_mbare_pilot import CLEAN_MBARE_PILOT
from function.list.coverage_new_code import COVERAGE_NEW_CODE
from function.list.git_check_clean import GIT_CHECK_CLEAN
from function.list.git_checkout_branches import GIT_CHECKOUT_BRANCHES
from function.list.git_fetch import GIT_FETCH
from function.list.git_log import GIT_LOG
from function.list.git_pull_all_repo_by_branch import GIT_PULL_ALL_REPO_BY_BRANCH
from function.list.git_pull_repo_by_branch import GIT_PULL_REPO_BY_BRANCH
from function.list.git_status import GIT_STATUS
from function.list.maven_parent_alignment import MAVEN_PARENT_ALIGNMENT
from function.list.run_tests import RUN_TESTS
from function.list.save_note import SAVE_NOTE
from function.spec import FunctionSpec

FUNCTION_REGISTRY: dict[str, FunctionSpec] = {
    spec.name: spec
    for spec in (
        GIT_STATUS,
        GIT_FETCH,
        GIT_LOG,
        GIT_PULL_ALL_REPO_BY_BRANCH,
        GIT_PULL_REPO_BY_BRANCH,
        MAVEN_PARENT_ALIGNMENT,
        COVERAGE_NEW_CODE,
        SAVE_NOTE,
        GIT_CHECK_CLEAN,
        GIT_CHECKOUT_BRANCHES,
        CLEAN_MBARE_PILOT,
        RUN_TESTS,
    )
}
"""Every function implemented in code, keyed by name."""


def get_function(name: str | None) -> FunctionSpec:
    if not name:
        raise ValidationError("Scegli la funzione da eseguire.")
    spec = FUNCTION_REGISTRY.get(name)
    if spec is None:
        raise ValidationError(f"La funzione {name} non esiste (più) nel codice.")
    return spec
