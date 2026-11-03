"""The agent task and its references as files in the repository Copilot works
on (``mbare-pilot/<task note>/``): rebuilt from scratch, never through a link."""
import os

import pytest

from core.error import ValidationError
from domain.project import task_folder

needs_symlinks = pytest.mark.skipif(os.name == "nt", reason="symlinks need extra rights on Windows")


def test_the_folder_is_named_after_the_task_note():
    assert task_folder.relative_folder("agent-task-login.md") == "mbare-pilot/agent-task-login"
    assert task_folder.relative_folder("agent-task-login") == "mbare-pilot/agent-task-login"


def test_write_rebuilds_only_the_tasks_folder(tmp_path):
    other = tmp_path / "mbare-pilot" / "agent-task-altro"
    other.mkdir(parents=True)
    (other / "task.md").write_text("altro", encoding="utf-8")

    first = task_folder.write(tmp_path, "agent-task-login.md", {"task.md": b"v1", "code-reference-a.md": b"a"})
    second = task_folder.write(tmp_path, "agent-task-login.md", {"task.md": b"v2"})

    assert first == second == (tmp_path / "mbare-pilot" / "agent-task-login").resolve()
    assert [item.name for item in second.iterdir()] == ["task.md"]  # the stale reference is gone
    assert (second / "task.md").read_bytes() == b"v2"
    assert (other / "task.md").read_text(encoding="utf-8") == "altro"


def test_file_names_cannot_leave_the_folder(tmp_path):
    folder = task_folder.write(tmp_path, "agent-task-x", {"../../fuori.md": b"no"})

    assert [item.name for item in folder.iterdir()] == ["fuori.md"]
    assert not (tmp_path / "fuori.md").exists()


@pytest.mark.parametrize("make", ["base", "task"])
def test_a_file_where_a_folder_should_be_is_an_error(tmp_path, make):
    if make == "base":
        (tmp_path / "mbare-pilot").write_text("file", encoding="utf-8")
    else:
        (tmp_path / "mbare-pilot").mkdir()
        (tmp_path / "mbare-pilot" / "agent-task-x").write_text("file", encoding="utf-8")

    with pytest.raises(ValidationError, match="deve essere una cartella"):
        task_folder.write(tmp_path, "agent-task-x", {"task.md": b"t"})


@needs_symlinks
@pytest.mark.parametrize("link", ["base", "task"])
def test_a_link_is_never_followed(tmp_path, link):
    repository, outside = tmp_path / "repo", tmp_path / "fuori"
    repository.mkdir()
    (outside / "agent-task-x").mkdir(parents=True)
    (outside / "agent-task-x" / "prezioso.txt").write_text("non cancellarmi", encoding="utf-8")
    if link == "base":
        (repository / "mbare-pilot").symlink_to(outside, target_is_directory=True)
    else:
        (repository / "mbare-pilot").mkdir()
        (repository / "mbare-pilot" / "agent-task-x").symlink_to(outside / "agent-task-x", target_is_directory=True)

    with pytest.raises(ValidationError, match="deve essere una cartella"):
        task_folder.write(repository, "agent-task-x", {"task.md": b"t"})
    assert (outside / "agent-task-x" / "prezioso.txt").is_file()


@pytest.mark.parametrize("path, inside", [
    ("mbare-pilot/", True),
    ("mbare-pilot/agent-task-x/task.md", True),
    ("api/mbare-pilot/agent-task-x/task.md", True),  # a repository below the git root
    ("src/mbare-pilot.py", False),
    ("mbare-pilot-notes.md", False),
    ("copilot.txt", False),
])
def test_git_status_paths_inside_the_task_folders(path, inside):
    assert task_folder.is_task_path(path) is inside


def test_uploaded_files_go_in_the_files_subfolder(tmp_path):
    folder = task_folder.write(tmp_path, "agent-task-x", {"task.md": b"t", "files/specifiche.pdf": b"%PDF", "altro/x.md": b"x"})

    assert (folder / "files" / "specifiche.pdf").read_bytes() == b"%PDF"
    assert (folder / "x.md").read_bytes() == b"x"  # any other folder part is dropped
