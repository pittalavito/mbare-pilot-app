"""Confluence Cloud client: spaces and pages via REST API v2, full-text search
via the v1 CQL endpoint (v2 has no search). Payloads are mapped to domain
models here; page bodies (storage XHTML) become plain text."""
from html.parser import HTMLParser
from typing import Any

from domain.client.atlassian.http import AtlassianHttp
from models.domain.atlassian import ConfluencePage, ConfluenceSearchHit, ConfluenceSpace


class ConfluenceClient:

    def __init__(self, http: AtlassianHttp):
        self._http = http

    def list_spaces(self, keys: list[str] | None = None, limit: int = 100) -> list[ConfluenceSpace]:
        params = {"keys": ",".join(keys) if keys else None, "status": "current"}
        return [self._to_space(raw) for raw in self._http.paginate_cursor("/wiki/api/v2/spaces", params, limit)]

    def get_space(self, key: str) -> ConfluenceSpace | None:
        spaces = self.list_spaces(keys=[key], limit=1)
        return spaces[0] if spaces else None

    def list_pages(self, space_id: str, limit: int = 100) -> list[ConfluencePage]:
        """Pages of a space (titles only, no body)."""
        path = f"/wiki/api/v2/spaces/{space_id}/pages"
        return [self._to_page(raw) for raw in self._http.paginate_cursor(path, {"status": "current"}, limit)]

    def get_page(self, page_id: str) -> ConfluencePage:
        """One page with its body as plain text."""
        return self._to_page(self._http.get(f"/wiki/api/v2/pages/{page_id}", {"body-format": "storage"}))

    def search_pages(self, text: str, space_key: str | None = None, limit: int = 25) -> list[ConfluenceSearchHit]:
        """Pages whose content matches ``text`` (CQL ``text ~``), optionally in one space."""
        cql = f'type = page AND text ~ "{_cql_escape(text)}"'
        if space_key:
            cql += f' AND space = "{_cql_escape(space_key)}"'
        body = self._http.get("/wiki/rest/api/search", {"cql": cql, "limit": min(limit, 100)})
        return [self._to_hit(raw) for raw in body.get("results", []) if raw.get("content")]

    # ------------------------------------------------------------ mapping
    def _url(self, webui: str | None) -> str:
        return f"{self._http.base_url}/wiki{webui}" if webui else f"{self._http.base_url}/wiki"

    def _to_space(self, raw: dict[str, Any]) -> ConfluenceSpace:
        return ConfluenceSpace(
            id=str(raw["id"]), key=raw["key"], name=raw.get("name", raw["key"]),
            space_type=raw.get("type"), url=self._url(raw.get("_links", {}).get("webui")),
        )

    def _to_page(self, raw: dict[str, Any]) -> ConfluencePage:
        storage = raw.get("body", {}).get("storage", {}).get("value", "")
        return ConfluencePage(
            id=str(raw["id"]), title=raw.get("title", ""), space_id=_str_or_none(raw.get("spaceId")),
            url=self._url(raw.get("_links", {}).get("webui")), body=storage_to_text(storage),
        )

    def _to_hit(self, raw: dict[str, Any]) -> ConfluenceSearchHit:
        content = raw["content"]
        return ConfluenceSearchHit(
            id=str(content["id"]), title=content.get("title", raw.get("title", "")),
            excerpt=storage_to_text(raw.get("excerpt", "")), url=self._url(raw.get("url")),
        )


def _str_or_none(value: Any) -> str | None:
    return str(value) if value is not None else None


def _cql_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


class _TextExtractor(HTMLParser):
    _BLOCKS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            self.parts.append("\n- ")
        elif tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def storage_to_text(html: str) -> str:
    """Plain text from Confluence storage format (XHTML with ac:/ri: macros)."""
    if not html:
        return ""
    parser = _TextExtractor()
    parser.feed(html)
    lines = [" ".join(line.split()) for line in "".join(parser.parts).splitlines()]
    return "\n".join(line for line in lines if line)
