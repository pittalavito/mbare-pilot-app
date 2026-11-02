"""Confluence Cloud client: spaces and pages via REST API v2, full-text search
via the v1 CQL endpoint (v2 has no search). Payloads are mapped to domain
models here; page bodies (storage XHTML) become Markdown."""
import re
from html import escape
from html.parser import HTMLParser
from typing import Any

from domain.client.atlassian.http import AtlassianHttp
from domain.client.atlassian.markdown import fenced, inline_code, join_blocks, prefix_lines, table, tidy
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
        """One page with its body as Markdown."""
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
            url=self._url(raw.get("_links", {}).get("webui")), body=storage_to_markdown(storage),
        )

    def _to_hit(self, raw: dict[str, Any]) -> ConfluenceSearchHit:
        content = raw["content"]
        return ConfluenceSearchHit(
            id=str(content["id"]), title=content.get("title", raw.get("title", "")),
            excerpt=storage_to_markdown(raw.get("excerpt", "")), url=self._url(raw.get("url")),
        )


def _str_or_none(value: Any) -> str | None:
    return str(value) if value is not None else None


def _cql_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


_CDATA = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.DOTALL)
_VOID = {"br", "hr", "img", "col", "ac:emoticon", "ac:parameter-void", "ri:page", "ri:attachment", "ri:url", "ri:user"}
_HEADINGS = {f"h{n}": n for n in range(1, 7)}
_CODE_MACROS = {"code", "noformat"}
_QUOTE_MACROS = {"info", "note", "warning", "tip", "panel", "expand", "excerpt", "section", "column"}


class _Node:
    def __init__(self, tag: str, attrs: dict[str, str]):
        self.tag = tag
        self.attrs = attrs
        self.children: list[_Node | str] = []

    def find(self, tag: str) -> "_Node | None":
        return next((c for c in self.children if isinstance(c, _Node) and c.tag == tag), None)

    def text(self) -> str:
        return "".join(c if isinstance(c, str) else c.text() for c in self.children)


class _TreeBuilder(HTMLParser):
    """Storage XHTML as a small tree (well-formed input; a stray end tag
    closes up to its match, an unknown one is ignored)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("root", {})
        self._stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, {k: v or "" for k, v in attrs})
        self._stack[-1].children.append(node)
        if tag not in _VOID:
            self._stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self._stack[-1].children.append(_Node(tag, {k: v or "" for k, v in attrs}))

    def handle_endtag(self, tag):
        for depth in range(len(self._stack) - 1, 0, -1):
            if self._stack[depth].tag == tag:
                del self._stack[depth:]
                return

    def handle_data(self, data):
        self._stack[-1].children.append(data)


def storage_to_markdown(storage: str) -> str:
    """Markdown from Confluence storage format (XHTML with ac:/ri: macros):
    headings, lists, tables, code macros (with their language), panels as
    quotes, links and inline marks. Unknown macros keep their text."""
    if not storage:
        return ""
    builder = _TreeBuilder()
    builder.feed(_CDATA.sub(lambda m: escape(m.group(1), quote=False), storage))
    builder.close()
    return tidy(_blocks(builder.root.children))


_BLOCK_TAGS = {
    "p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "table", "pre", "blockquote", "hr",
    "ac:structured-macro", "ac:task-list", "ac:layout", "ac:layout-section", "ac:layout-cell",
    "ac:rich-text-body", "section",
}


def _blocks(children: list["_Node | str"]) -> str:
    """Block children one after the other; runs of inline content stay together."""
    blocks: list[str] = []
    run: list[_Node | str] = []
    for child in children:
        if isinstance(child, _Node) and child.tag in _BLOCK_TAGS:
            if run:
                blocks.append(_inlines(run).strip())
                run = []
            blocks.append(_block(child))
        else:
            run.append(child)
    if run:
        blocks.append(_inlines(run).strip())
    return join_blocks(blocks)


def _block(node: _Node) -> str:
    tag = node.tag
    if tag in _HEADINGS:
        return f"{'#' * _HEADINGS[tag]} {_inlines(node.children).strip()}"
    if tag == "p":
        return _inlines(node.children).strip()
    if tag in ("ul", "ol"):
        return _list(node)
    if tag == "table":
        return table([[_cell(cell) for cell in _children(row, "th", "td")] for row in _rows(node)])
    if tag == "pre":
        return fenced(node.text())
    if tag == "blockquote":
        return prefix_lines(_blocks(node.children), "> ", "> ")
    if tag == "hr":
        return "---"
    if tag == "ac:task-list":
        return _tasks(node)
    if tag == "ac:structured-macro":
        return _macro(node)
    return _blocks(node.children)


def _macro(node: _Node) -> str:
    name = node.attrs.get("ac:name", "")
    params = {p.attrs.get("ac:name", ""): p.text() for p in _children(node, "ac:parameter")}
    plain = node.find("ac:plain-text-body")
    rich = node.find("ac:rich-text-body")
    if name in _CODE_MACROS or (plain is not None and rich is None):
        return fenced(plain.text() if plain is not None else "", params.get("language", ""))
    if rich is None:
        return ""
    body = _blocks(rich.children)
    if name in _QUOTE_MACROS:
        title = params.get("title", "").strip()
        return prefix_lines(join_blocks([f"**{title}**" if title else "", body]), "> ", "> ")
    return body


def _list(node: _Node) -> str:
    ordered = node.tag == "ol"
    items = []
    for index, item in enumerate(_children(node, "li"), start=1):
        marker = f"{index}. " if ordered else "- "
        items.append(prefix_lines(_blocks(item.children) or "", marker, " " * len(marker)))
    return "\n".join(items)


def _tasks(node: _Node) -> str:
    items = []
    for task in _children(node, "ac:task"):
        status = task.find("ac:task-status")
        box = "[x] " if status is not None and status.text().strip() == "complete" else "[ ] "
        body = task.find("ac:task-body")
        items.append(prefix_lines(_blocks(body.children) if body is not None else "", "- " + box, "  "))
    return "\n".join(items)


def _rows(table_node: _Node) -> list[_Node]:
    rows: list[_Node] = []
    for child in table_node.children:
        if isinstance(child, _Node):
            if child.tag == "tr":
                rows.append(child)
            elif child.tag in ("thead", "tbody", "tfoot"):
                rows += _children(child, "tr")
    return rows


def _cell(cell: _Node) -> str:
    """A table cell on one line: its blocks and line breaks joined by a space."""
    return " ".join(_blocks(cell.children).replace("\\\n", "\n").split("\n"))


def _children(node: _Node, *tags: str) -> list[_Node]:
    return [c for c in node.children if isinstance(c, _Node) and c.tag in tags]


def _inlines(children: list["_Node | str"]) -> str:
    return _squash("".join(_inline(child) for child in children))


def _squash(text: str) -> str:
    """HTML whitespace: runs collapse to one space (edges included: ``<b>a
    </b>b`` keeps its space); hard breaks (``\\`` + newline) stay."""
    return "\\\n".join(re.sub(r"\s+", " ", line) for line in text.split("\\\n"))


def _inline(node: "_Node | str") -> str:
    if isinstance(node, str):
        return node
    tag = node.tag
    if tag == "br":
        return "\\\n"
    if tag in ("strong", "b"):
        return _wrap(_inlines(node.children), "**")
    if tag in ("em", "i"):
        return _wrap(_inlines(node.children), "*")
    if tag in ("s", "del", "strike"):
        return _wrap(_inlines(node.children), "~~")
    if tag == "code":
        return inline_code(node.text())
    if tag == "a":
        label, href = _inlines(node.children).strip(), node.attrs.get("href", "")
        return f"[{label or href}]({href})" if href else label
    if tag == "ac:link":
        body = node.find("ac:link-body") or node.find("ac:plain-text-link-body")
        target = node.find("ri:page") or node.find("ri:attachment") or node.find("ri:user")
        if body is not None:
            return body.text()
        if target is not None:
            return target.attrs.get("ri:content-title") or target.attrs.get("ri:filename") or ""
        return ""
    if tag == "ac:emoticon":
        return node.attrs.get("ac:emoji-fallback", "")
    if tag in ("ac:image", "ac:parameter", "img", "ac:placeholder"):
        return ""
    if tag in _BLOCK_TAGS:
        return " " + _block(node) + " "
    return _inlines(node.children)


def _wrap(text: str, mark: str) -> str:
    """``mark`` around the text, outside its edge spaces (``** x**`` is not bold)."""
    if not text.strip():
        return text
    lead, trail = text[: len(text) - len(text.lstrip())], text[len(text.rstrip()):]
    return f"{lead}{mark}{text.strip()}{mark}{trail}"
