"""A draft written in Markdown (``bozza-<task>.md``) as Confluence and Jira
want it: storage format (XHTML) for a Confluence page, ADF (Atlassian
Document Format) for a Jira description. Pure functions.

What converts: ``#`` headings, paragraphs, bullet and numbered lists (a
checkbox item becomes a bullet; nested items are flattened), fenced code,
GFM tables, ``>`` quotes, ``---`` rules; inline ``**bold**``, ``*italic*`` /
``_italic_``, `` `code` `` and ``[text](url)``. Anything else stays as text.
A ``# title`` on the first line is the page's or issue's title, not body
(``split_title``)."""
import re
from dataclasses import dataclass, field
from html import escape
from typing import Any

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_BULLET = re.compile(r"^\s*[-*+]\s+(?:\[[ xX]\]\s+)?(.*)$")
_NUMBERED = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})\s*([\w+-]*)\s*$")
_RULE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
_INLINE = re.compile(r"(`+)(.+?)\1|\*\*(.+?)\*\*|__(.+?)__|\[([^\]]+)\]\(([^)\s]+)\)|\*(?!\s)(.+?)(?<!\s)\*|(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)")


@dataclass
class Block:
    kind: str
    """heading, paragraph, bullets, numbers, code, table, quote, rule."""
    text: str = ""
    level: int = 0
    language: str = ""
    items: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)


def split_title(markdown: str, fallback: str) -> tuple[str, str]:
    """The ``# title`` of the first non-empty line, and the rest; ``fallback`` when there is none."""
    lines = markdown.strip().splitlines()
    if lines and (match := _HEADING.match(lines[0])) and len(match.group(1)) == 1:
        return match.group(2).strip() or fallback, "\n".join(lines[1:]).strip()
    return fallback, markdown.strip()


def blocks(markdown: str) -> list[Block]:
    lines = markdown.replace("\r\n", "\n").split("\n")
    found: list[Block] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
        elif fence := _FENCE.match(line):
            end = next((i for i in range(index + 1, len(lines)) if lines[i].strip().startswith(fence.group(1))), len(lines))
            found.append(Block("code", text="\n".join(lines[index + 1:end]), language=fence.group(2)))
            index = end + 1
        elif heading := _HEADING.match(line):
            found.append(Block("heading", text=heading.group(2), level=len(heading.group(1))))
            index += 1
        elif _RULE.match(line):
            found.append(Block("rule"))
            index += 1
        elif "|" in line and index + 1 < len(lines) and _TABLE_SEPARATOR.match(lines[index + 1]):
            end = index + 2
            while end < len(lines) and "|" in lines[end] and lines[end].strip():
                end += 1
            found.append(Block("table", rows=[_cells(row) for row in [lines[index], *lines[index + 2:end]]]))
            index = end
        elif line.lstrip().startswith(">"):
            end = index
            while end < len(lines) and lines[end].lstrip().startswith(">"):
                end += 1
            found.append(Block("quote", text=" ".join(row.lstrip()[1:].strip() for row in lines[index:end])))
            index = end
        elif _BULLET.match(line) or _NUMBERED.match(line):
            pattern = _BULLET if _BULLET.match(line) else _NUMBERED
            items = []
            while index < len(lines) and (match := (_BULLET.match(lines[index]) or _NUMBERED.match(lines[index]))):
                items.append(match.group(1).strip())
                index += 1
            found.append(Block("bullets" if pattern is _BULLET else "numbers", items=items))
        else:
            end = index
            while end < len(lines) and lines[end].strip() and not _starts_block(lines, end):
                end += 1
            found.append(Block("paragraph", text=" ".join(row.strip() for row in lines[index:max(end, index + 1)])))
            index = max(end, index + 1)
    return found


def _starts_block(lines: list[str], index: int) -> bool:
    line = lines[index]
    return bool(_FENCE.match(line) or _HEADING.match(line) or _RULE.match(line) or _BULLET.match(line) or _NUMBERED.match(line)
                or line.lstrip().startswith(">")
                or ("|" in line and index + 1 < len(lines) and _TABLE_SEPARATOR.match(lines[index + 1])))


def _cells(row: str) -> list[str]:
    row = row.strip()
    row = row[1:] if row.startswith("|") else row
    row = row[:-1] if row.endswith("|") and not row.endswith("\\|") else row
    return [cell.strip().replace("\\|", "|") for cell in re.split(r"(?<!\\)\|", row)]


# ------------------------------------------------------------------ inline

def _inline_parts(text: str) -> list[tuple[str, str, str]]:
    """``(kind, text, href)`` runs: text, code, strong, em, link."""
    parts, position = [], 0
    for match in _INLINE.finditer(text):
        if match.start() > position:
            parts.append(("text", text[position:match.start()], ""))
        if match.group(2) is not None:
            parts.append(("code", match.group(2).strip(), ""))
        elif match.group(3) is not None or match.group(4) is not None:
            parts.append(("strong", match.group(3) or match.group(4), ""))
        elif match.group(5) is not None:
            parts.append(("link", match.group(5), match.group(6)))
        else:
            parts.append(("em", match.group(7) or match.group(8), ""))
        position = match.end()
    if position < len(text):
        parts.append(("text", text[position:], ""))
    return parts


# ------------------------------------------------------------------ storage

def to_storage(markdown: str) -> str:
    """Confluence storage format (XHTML)."""
    return "".join(_storage_block(block) for block in blocks(markdown))


def _storage_inline(text: str) -> str:
    out = []
    for kind, value, href in _inline_parts(text):
        if kind == "code":
            out.append(f"<code>{escape(value)}</code>")
        elif kind == "strong":
            out.append(f"<strong>{escape(value)}</strong>")
        elif kind == "em":
            out.append(f"<em>{escape(value)}</em>")
        elif kind == "link":
            out.append(f'<a href="{escape(href)}">{escape(value)}</a>')
        else:
            out.append(escape(value))
    return "".join(out)


def _storage_block(block: Block) -> str:
    if block.kind == "heading":
        return f"<h{block.level}>{_storage_inline(block.text)}</h{block.level}>"
    if block.kind == "code":
        language = f'<ac:parameter ac:name="language">{escape(block.language)}</ac:parameter>' if block.language else ""
        code = block.text.replace("]]>", "]]]]><![CDATA[>")
        return f'<ac:structured-macro ac:name="code">{language}<ac:plain-text-body><![CDATA[{code}]]></ac:plain-text-body></ac:structured-macro>'
    if block.kind in ("bullets", "numbers"):
        tag = "ul" if block.kind == "bullets" else "ol"
        return f"<{tag}>" + "".join(f"<li>{_storage_inline(item)}</li>" for item in block.items) + f"</{tag}>"
    if block.kind == "table":
        header, *body = block.rows
        rows = ["<tr>" + "".join(f"<th>{_storage_inline(cell)}</th>" for cell in header) + "</tr>"]
        rows += ["<tr>" + "".join(f"<td>{_storage_inline(cell)}</td>" for cell in row) + "</tr>" for row in body]
        return "<table><tbody>" + "".join(rows) + "</tbody></table>"
    if block.kind == "quote":
        return f"<blockquote><p>{_storage_inline(block.text)}</p></blockquote>"
    if block.kind == "rule":
        return "<hr />"
    return f"<p>{_storage_inline(block.text)}</p>"


# ---------------------------------------------------------------------- ADF

def to_adf(markdown: str) -> dict[str, Any]:
    """A Jira Cloud (REST v3) document."""
    return {"type": "doc", "version": 1, "content": [_adf_block(block) for block in blocks(markdown)]}


def _adf_inline(text: str) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for kind, value, href in _inline_parts(text):
        if not value:
            continue
        node: dict[str, Any] = {"type": "text", "text": value}
        marks = {"code": [{"type": "code"}], "strong": [{"type": "strong"}], "em": [{"type": "em"}],
                 "link": [{"type": "link", "attrs": {"href": href}}]}.get(kind)
        if marks:
            node["marks"] = marks
        nodes.append(node)
    return nodes


def _paragraph(text: str) -> dict[str, Any]:
    content = _adf_inline(text)
    return {"type": "paragraph", "content": content} if content else {"type": "paragraph"}


def _adf_block(block: Block) -> dict[str, Any]:
    if block.kind == "heading":
        return {"type": "heading", "attrs": {"level": block.level}, "content": _adf_inline(block.text)}
    if block.kind == "code":
        node: dict[str, Any] = {"type": "codeBlock", "content": [{"type": "text", "text": block.text}] if block.text else []}
        if block.language:
            node["attrs"] = {"language": block.language}
        return node
    if block.kind in ("bullets", "numbers"):
        return {"type": "bulletList" if block.kind == "bullets" else "orderedList",
                "content": [{"type": "listItem", "content": [_paragraph(item)]} for item in block.items]}
    if block.kind == "table":
        header, *body = block.rows
        rows = [{"type": "tableRow", "content": [{"type": "tableHeader", "content": [_paragraph(cell)]} for cell in header]}]
        rows += [{"type": "tableRow", "content": [{"type": "tableCell", "content": [_paragraph(cell)]} for cell in row]} for row in body]
        return {"type": "table", "content": rows}
    if block.kind == "quote":
        return {"type": "blockquote", "content": [_paragraph(block.text)]}
    if block.kind == "rule":
        return {"type": "rule"}
    return _paragraph(block.text)
