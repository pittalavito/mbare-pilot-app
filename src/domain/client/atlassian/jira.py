"""Jira Cloud client (REST API v3): projects, JQL search, single issue.
Payloads are mapped to domain models here, so nothing above this layer sees
Jira's JSON. Rich text (ADF) becomes Markdown."""
from datetime import datetime
from typing import Any

from domain.client.atlassian.http import AtlassianHttp
from domain.client.atlassian.markdown import fenced, inline_code, join_blocks, prefix_lines, table, tidy
from models.domain.atlassian import AtlassianUser, JiraIssue, JiraProject

_ISSUE_FIELDS = "summary,status,issuetype,priority,assignee,updated,description"


class JiraClient:

    def __init__(self, http: AtlassianHttp):
        self._http = http

    def myself(self) -> AtlassianUser:
        body = self._http.get("/rest/api/3/myself")
        return AtlassianUser(
            account_id=body["accountId"], display_name=body.get("displayName", ""), email=body.get("emailAddress"),
        )

    def list_projects(self, query: str | None = None, limit: int = 100) -> list[JiraProject]:
        """Projects visible to the token, optionally filtered by name/key."""
        params = {"query": query, "orderBy": "name"}
        return [self._to_project(raw) for raw in self._http.paginate_offset("/rest/api/3/project/search", params, limit)]

    def search_issues(self, jql: str, limit: int = 50) -> list[JiraIssue]:
        """Issues matching ``jql`` (``/search/jql``, token-based pagination)."""
        issues: list[JiraIssue] = []
        next_token: str | None = None
        while len(issues) < limit:
            body = self._http.get("/rest/api/3/search/jql", {
                "jql": jql,
                "fields": _ISSUE_FIELDS,
                "maxResults": min(100, limit - len(issues)),
                "nextPageToken": next_token,
            })
            issues += [self._to_issue(raw) for raw in body.get("issues", [])]
            next_token = body.get("nextPageToken")
            if body.get("isLast", True) or not next_token:
                break
        return issues[:limit]

    def get_issue(self, key: str) -> JiraIssue:
        return self._to_issue(self._http.get(f"/rest/api/3/issue/{key}", {"fields": _ISSUE_FIELDS}))

    # ------------------------------------------------------------ mapping
    def _to_project(self, raw: dict[str, Any]) -> JiraProject:
        return JiraProject(
            id=str(raw["id"]),
            key=raw["key"],
            name=raw.get("name", raw["key"]),
            project_type=raw.get("projectTypeKey"),
            url=f"{self._http.base_url}/browse/{raw['key']}",
        )

    def _to_issue(self, raw: dict[str, Any]) -> JiraIssue:
        fields = raw.get("fields", {})
        updated = fields.get("updated")
        return JiraIssue(
            key=raw["key"],
            summary=fields.get("summary", ""),
            status=_name(fields.get("status")),
            issue_type=_name(fields.get("issuetype")),
            priority=_name(fields.get("priority")),
            assignee=(fields.get("assignee") or {}).get("displayName"),
            updated=datetime.strptime(updated, "%Y-%m-%dT%H:%M:%S.%f%z") if updated else None,
            description=adf_to_markdown(fields.get("description")),
            url=f"{self._http.base_url}/browse/{raw['key']}",
        )


def _name(value: dict[str, Any] | None) -> str | None:
    return value.get("name") if value else None


def adf_to_markdown(node: Any) -> str:
    """Markdown from an Atlassian Document Format node (Jira v3 rich text):
    headings, lists, tables, code blocks (with their language), quotes and
    panels, links and inline marks. Unknown nodes keep their text."""
    if not node:
        return ""
    if isinstance(node, str):
        return node
    return tidy(_block(node))


def _block(node: dict[str, Any]) -> str:
    kind = node.get("type")
    children = node.get("content", [])
    if kind == "paragraph":
        return _inlines(children)
    if kind == "heading":
        level = min(max(int(node.get("attrs", {}).get("level", 1)), 1), 6)
        return f"{'#' * level} {_inlines(children)}"
    if kind in ("bulletList", "orderedList"):
        start = int(node.get("attrs", {}).get("order", 1)) if kind == "orderedList" else 0
        items = []
        for index, item in enumerate(children):
            marker = f"{start + index}. " if kind == "orderedList" else "- "
            items.append(prefix_lines(_blocks(item.get("content", [])), marker, " " * len(marker)))
        return "\n".join(items)
    if kind == "taskList":
        items = []
        for item in children:
            box = "[x] " if item.get("attrs", {}).get("state") == "DONE" else "[ ] "
            body = _inlines(item.get("content", [])) if item.get("type") == "taskItem" else _block(item)
            items.append(prefix_lines(body, "- " + box, "  "))
        return "\n".join(items)
    if kind == "codeBlock":
        code = "".join(child.get("text", "") for child in children)
        return fenced(code, node.get("attrs", {}).get("language") or "")
    if kind in ("blockquote", "panel"):
        return prefix_lines(_blocks(children), "> ", "> ")
    if kind == "rule":
        return "---"
    if kind == "table":
        return table([
            [_cell(cell) for cell in row.get("content", [])]
            for row in children if row.get("type") == "tableRow"
        ])
    if kind in ("mediaSingle", "mediaGroup", "media"):
        return ""
    if kind in _INLINE_NODES:
        return _inline(node)
    return _blocks(children)


def _blocks(nodes: list[dict[str, Any]]) -> str:
    """Block nodes one after the other; runs of inline nodes stay on one line."""
    blocks: list[str] = []
    run: list[dict[str, Any]] = []
    for child in nodes:
        if child.get("type") in _INLINE_NODES:
            run.append(child)
            continue
        if run:
            blocks.append(_inlines(run))
            run = []
        blocks.append(_block(child))
    if run:
        blocks.append(_inlines(run))
    return join_blocks(blocks)


def _cell(cell: dict[str, Any]) -> str:
    """A table cell on one line: its blocks and line breaks joined by a space."""
    return " ".join(_blocks(cell.get("content", [])).replace("\\\n", "\n").split("\n"))


def _inlines(nodes: list[dict[str, Any]]) -> str:
    return "".join(_inline(child) for child in nodes)


_INLINE_NODES = {"text", "hardBreak", "mention", "emoji", "inlineCard", "date", "status", "inlineExtension"}


def _inline(node: dict[str, Any]) -> str:
    kind = node.get("type")
    attrs = node.get("attrs", {})
    if kind == "text":
        return _marked(node.get("text", ""), node.get("marks", []))
    if kind == "hardBreak":
        return "\\\n"
    if kind == "mention":
        return attrs.get("text", "")
    if kind == "emoji":
        return attrs.get("text") or attrs.get("shortName", "")
    if kind == "inlineCard":
        url = attrs.get("url", "")
        return f"<{url}>" if url else ""
    if kind == "status":
        return f"[{attrs.get('text', '')}]"
    if kind == "date":
        stamp = attrs.get("timestamp")
        return datetime.fromtimestamp(int(stamp) / 1000).strftime("%Y-%m-%d") if stamp else ""
    return _inlines(node.get("content", []))


def _marked(text: str, marks: list[dict[str, Any]]) -> str:
    kinds = {mark.get("type"): mark for mark in marks}
    if "code" in kinds:
        text = inline_code(text)
    if "strong" in kinds:
        text = f"**{text}**"
    if "em" in kinds:
        text = f"*{text}*"
    if "strike" in kinds:
        text = f"~~{text}~~"
    if "link" in kinds:
        href = kinds["link"].get("attrs", {}).get("href", "")
        if href:
            text = f"[{text}]({href})"
    return text
