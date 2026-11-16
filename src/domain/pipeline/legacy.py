"""The function steps of before the one registry (plan 15): read as tool
steps. A function's parameters become the tool's arguments; what the function
took from the step input or the run input becomes a placeholder argument
(``{input}``, ``{pipeline_input}``). Pure functions."""
from typing import Any

INPUT = "{input}"
PIPELINE_INPUT = "{pipeline_input}"

_RENAMED = {"git_pull_all_repo_by_branch": "git_pull_all_by_branch", "git_pull_repo_by_branch": "git_pull_by_branch"}
TOOL_NAMES_RENAMED = {"list_functions": "list_tools", "create_function_task": "create_tool_task"}
"""The Architect's tools renamed with the functions (a chatbot saved with the old names gets the new ones)."""


def function_as_tool(function: str, params: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """The tool and its arguments for a function step of before."""
    args = dict(params)
    if function in ("git_status", "git_fetch", "git_log", "coverage_new_code"):
        args["repository"] = str(args.get("repository") or "").strip() or INPUT
    elif function == "git_pull_all_repo_by_branch":
        args["branch"] = str(args.get("branch") or "").strip() or INPUT
    elif function == "git_pull_repo_by_branch" and not str(args.get("repository") or "").strip():
        args["repository"] = INPUT  # the input was «<repository> [<branch>]»: the branch stays the param
    elif function == "save_note":
        args["content"] = INPUT
    elif function in ("git_check_clean", "git_checkout_branches"):
        args["targets"] = PIPELINE_INPUT
    elif function in ("clean_mbare_pilot", "run_tests"):
        args["target"] = PIPELINE_INPUT
    return _RENAMED.get(function, function), args
