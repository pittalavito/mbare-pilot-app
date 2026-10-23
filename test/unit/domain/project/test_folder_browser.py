import pytest

from core.error import ValidationError
from domain.project.folder_browser import FolderBrowser


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "root"
    (root / "alpha" / "src").mkdir(parents=True)
    (root / "beta").mkdir()
    (root / ".hidden").mkdir()
    (root / "alpha" / "README.md").write_text("x", encoding="utf-8")
    (root / "alpha" / "src" / "main.py").write_text("x", encoding="utf-8")
    (root / "alpha" / "node_modules" / "pkg").mkdir(parents=True)
    return root


@pytest.fixture
def browser(root):
    return FolderBrowser([root])


def test_resolve_folder_inside_root(browser, root):
    assert browser.resolve(root / "alpha") == (root / "alpha").resolve()
    assert browser.resolve(f'  "{root / "beta"}"  ') == (root / "beta").resolve()


@pytest.mark.parametrize("path", ["", "../", "alpha/../../"])
def test_resolve_rejects_empty_and_outside_root(browser, root, path):
    with pytest.raises(ValidationError):
        browser.resolve(root / path if path else path)


def test_resolve_rejects_missing_folder_and_files(browser, root):
    with pytest.raises(ValidationError):
        browser.resolve(root / "missing")
    with pytest.raises(ValidationError):
        browser.resolve(root / "alpha" / "README.md")


def test_subfolders_sorted_and_hidden_on_request(browser, root):
    assert [p.name for p in browser.subfolders(root)] == ["alpha", "beta"]
    assert [p.name for p in browser.subfolders(root, show_hidden=True)] == [".hidden", "alpha", "beta"]


def test_parent_stops_at_root(browser, root):
    assert browser.parent((root / "alpha").resolve()) == root.resolve()
    assert browser.parent(root.resolve()) is None


def test_create_folder(browser, root):
    created = browser.create_folder(root, "gamma")

    assert created.is_dir() and created.parent == root.resolve()


@pytest.mark.parametrize("name", ["", "..", "a/b", "a\\b", "bad:name", "alpha"])
def test_create_folder_rejects_invalid_or_existing(browser, root, name):
    with pytest.raises(ValidationError):
        browser.create_folder(root, name)
