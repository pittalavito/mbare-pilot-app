"""Jira Cloud client (REST API v3): projects, JQL search, single issue.
Payloads are mapped to domain models here, so nothing above this layer sees
Jira's JSON."""
from datetime import datetime
from typing import Any

from domain.client.atlassian.http import AtlassianHttp
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
            description=adf_to_text(fields.get("description")),
            url=f"{self._http.base_url}/browse/{raw['key']}",
        )


def _name(value: dict[str, Any] | None) -> str | None:
    return value.get("name") if value else None


_BLOCK_NODES = {"paragraph", "heading", "listItem", "blockquote", "codeBlock", "tableRow", "rule"}


def adf_to_text(node: Any) -> str:
    """Plain text from an Atlassian Document Format node (Jira v3 rich text):
    text nodes concatenated, one line per block, list items prefixed by "- "."""
    if not node:
        return ""
    if isinstance(node, str):
        return node
    parts: list[str] = []

    def walk(current: dict[str, Any]) -> None:
        kind = current.get("type")
        if kind == "text":
            parts.append(current.get("text", ""))
        elif kind == "hardBreak":
            parts.append("\n")
        elif kind == "mention":
            parts.append(current.get("attrs", {}).get("text", ""))
        if kind == "listItem":
            parts.append("- ")
        for child in current.get("content", []):
            walk(child)
        if kind in _BLOCK_NODES:
            parts.append("\n")

    walk(node)
    lines = [line.rstrip() for line in "".join(parts).splitlines()]
    return "\n".join(line for line in lines if line).strip()
