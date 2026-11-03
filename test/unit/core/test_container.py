import datapizza.tracing
import fakeredis
import pytest

from config import Config
from core.container import Container
from domain.store.redis.repository import Client


@pytest.mark.parametrize("enabled", [True, False])
def test_trace_summary_setting_controls_datapizza_console(enabled, config, tmp_path, monkeypatch):
    monkeypatch.setattr(Client, "create_redis_client", staticmethod(lambda url: fakeredis.FakeRedis(decode_responses=True)))
    Config.set(config.model_copy(update={"mbare_pilot_home": str(tmp_path), "datapizza_trace_summary": enabled}))

    Container()

    assert datapizza.tracing.console.quiet is (not enabled)


def test_get_loads_once_and_set_replaces(config):
    assert Config.get() is config
    other = config.model_copy(update={"app_log_level": "DEBUG"})

    Config.set(other)

    assert Config.get() is other


def test_a_container_in_the_tests_never_reaches_the_real_copilot_cli(stores):
    """The real CLI spends AI credits: the tests' Config points to a command that does not exist."""
    from core.container import Container

    assert not Container(stores=stores).copilot_service._client.available


def test_at_startup_the_old_todo_lists_become_activities(stores, project_store, files_repository, monkeypatch):
    from core.error import ValidationError
    from models.domain.project import Project, ProjectSource
    from service.project_data_service import ProjectDataService

    for name in ("acme", "rotto"):
        project_store.save(Project(name=name, source=ProjectSource.FOLDER, root_path=f"/code/{name}"))
    notes = files_repository.root / "acme" / "notes"
    notes.mkdir(parents=True)
    (notes / "todo-list-rilascio.md").write_text("# Rilascio\n\n- [x] tag\n", encoding="utf-8")
    real = ProjectDataService.migrate_todo_lists

    def migrate(self, project_name):
        if project_name == "rotto":
            raise ValidationError("non leggibile")  # logged: the app starts anyway
        return real(self, project_name)

    monkeypatch.setattr(ProjectDataService, "migrate_todo_lists", migrate)
    container = Container(stores=stores)

    [(name, activity)] = container.project_data_service.activities("acme")
    assert (name, activity.status.value) == ("attivita-rilascio.md", "done")
    assert not (notes / "todo-list-rilascio.md").exists()
