"""The server: the API under /api (its lifespan runs, so the container is
there), the built frontend at every other path, a hint when it is not built."""
import pytest
from fastapi.testclient import TestClient

from core.container import Container
from core.server import create_server


@pytest.fixture
def dist(tmp_path):
    folder = tmp_path / "dist"
    (folder / "assets").mkdir(parents=True)
    (folder / "index.html").write_text("<div id=root></div>", encoding="utf-8")
    (folder / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("fuori", encoding="utf-8")
    return folder


def _client(dist, store_service):
    return TestClient(create_server(dist, Container(store_service=store_service)))


def test_the_api_answers_under_api_with_its_container(dist, store_service):
    with _client(dist, store_service) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        assert client.get("/api/projects").status_code == 200  # needs the container of the lifespan
        assert client.get("/api/nope").status_code == 404


def test_the_pages_of_the_app_get_index_html_and_files_are_served(dist, store_service):
    with _client(dist, store_service) as client:
        page = client.get("/projects/acme/chat")
        assert page.status_code == 200
        assert "id=root" in page.text
        assert client.get("/assets/app.js").text == "console.log(1)"
        assert client.get("/assets/missing.js").status_code == 404
        assert "fuori" not in client.get("/../secret.txt").text


def test_without_a_build_it_says_how_to_make_one(tmp_path, store_service):
    with _client(tmp_path / "dist", store_service) as client:
        response = client.get("/")
        assert response.status_code == 503
        assert "run-app.py" in response.text
        assert client.get("/api/health").status_code == 200
