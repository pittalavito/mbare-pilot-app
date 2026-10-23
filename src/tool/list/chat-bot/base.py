
"""Example tool: deterministic greeting."""
from datapizza.tools import tool

from models.domain.tool import HelloWorldResponse


@tool
def list_automatation(name: str) -> str:
    
    return ""


