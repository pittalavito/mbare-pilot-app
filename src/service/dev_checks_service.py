"""The tests' settings of a project (blocco 09): the command detected for each
repository, the one written in its place and the default scope (``run_tests``
reads them), and the Operator chosen for the project. The automations around
Copilot («Prepara sviluppo», «Verifica sviluppo») are gone (plan 22): that
work is a development's Pre and Post (plan 34), done automatically, by Dev or by hand."""
from domain.dev import tests
from models.domain.dev import DevSettings, RepositoryTests, TestScope
from service.git_service import GitService
from service.project_data_service import ProjectDataService


class DevChecksService:

    def __init__(self, git: GitService, project_data: ProjectDataService):
        self._git = git
        self._data = project_data

    # -------------------------------------------------------------- settings
    def settings(self, project_name: str) -> DevSettings:
        commands = self._data.test_commands(project_name)
        repositories = []
        for repository in self._git.repositories(project_name):
            root = self._git.repository_folder(project_name, repository.path)
            files = {path.name for path in root.iterdir()}
            kind = tests.detect(files)
            repositories.append(RepositoryTests(repository=repository.path, kind=kind, detected_command=tests.default_command(kind, files),
                                                command=commands.get(repository.path, "")))
        return DevSettings(test_scope=self._data.test_scope(project_name), repositories=repositories)

    def operator_chatbot_id(self, project_name: str) -> int | None:
        """The Operator chosen for the preparation (None = the project's first one)."""
        return self._data.operator_chatbot_id(project_name)

    def save_operator(self, project_name: str, chatbot_id: int | None) -> None:
        self._data.save_operator_chatbot_id(project_name, chatbot_id)

    def save_settings(self, project_name: str, scope: TestScope, commands: dict[str, str]) -> DevSettings:
        self._data.save_test_settings(project_name, scope, commands)
        return self.settings(project_name)
