"""Example tool: deterministic greeting."""
from datapizza.tools import tool

from models.domain.tool import HelloWorldResponse


@tool
def hello_world(name: str) -> str:
    """Returns a greeting message for the given name."""
    return HelloWorldResponse(response=f"Hello, {name}!").model_dump_json()
