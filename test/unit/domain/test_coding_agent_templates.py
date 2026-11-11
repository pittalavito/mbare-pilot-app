"""Blocco 10: the drafts' templates (coding-agent/templates/<type>.md), the
project's over the global ones, put where a prompt writes {template}."""
from domain.project import coding_agent
from models.domain.note import TaskType

GLOBAL = "plan_prompt: \"Piano {task_folder}\"\nexecute_prompt: Vai\ndenied_tools: []\n"


class Files:
    def __init__(self, files: dict[str, str]):
        self._files = files

    def read_definition(self, path):
        return self._files.get(path)

    def list_definitions(self, folder):
        return [path for path in self._files if path.rsplit("/", 1)[0] == folder]


def test_templates_by_type_and_the_project_wins():
    files = Files({
        "global-coding-agent.yml": GLOBAL,
        "coding-agent/confluence.md": "Pagina in {task_folder}:\n{template}",
        "coding-agent/templates/confluence.md": "## Contesto\n",
        "coding-agent/templates/jira.md": "## Descrizione\n",
        "coding-agent/templates/altro.md": "ignorato",
        "project/acme/coding-agent/templates/jira.md": "## Storia\n",
    })

    settings = coding_agent.load(files, "acme")

    assert settings.templates == {TaskType.CONFLUENCE: "## Contesto", TaskType.JIRA: "## Storia"}
    assert "templates/confluence" not in settings.prompts and list(settings.prompts) == ["confluence"]
    assert coding_agent.plan_prompt(settings, "mbare-pilot/t", "confluence", TaskType.CONFLUENCE) == "Pagina in mbare-pilot/t:\n## Contesto"
    assert coding_agent.plan_prompt(settings, "mbare-pilot/t", "confluence", TaskType.ANALYSIS).endswith("(nessun template: scegli tu le sezioni)")
    assert coding_agent.plan_prompt(settings, "mbare-pilot/t") == "Piano mbare-pilot/t"
