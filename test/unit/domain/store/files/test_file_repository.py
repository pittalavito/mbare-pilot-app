import pytest

from core.error import NotFoundError, ValidationError


def test_save_read_list_delete(files_repository):
    stored = files_repository.save("uploads/a.txt", b"hello")

    assert stored.file_id == "uploads/a.txt"
    assert files_repository.read("uploads/a.txt") == b"hello"
    assert [f.file_id for f in files_repository.list()] == ["uploads/a.txt"]
    assert files_repository.delete("uploads/a.txt") is True
    assert files_repository.get("uploads/a.txt") is None


def test_read_missing_raises(files_repository):
    with pytest.raises(NotFoundError):
        files_repository.read("missing.txt")


@pytest.mark.parametrize("file_id", ["../escape.txt", "a/../../escape.txt", ""])
def test_path_traversal_rejected(files_repository, file_id):
    with pytest.raises(ValidationError):
        files_repository.save(file_id, b"x")
