"""Markdown building blocks shared by the Jira (ADF) and Confluence (storage)
converters: GitHub-flavored, as the frontend's ``Markdown`` component renders
it and as the agents read it in the references."""


def fenced(code: str, language: str = "") -> str:
    """A fenced code block; the fence is longer than any backtick run in ``code``."""
    longest = run = 0
    for char in code:
        run = run + 1 if char == "`" else 0
        longest = max(longest, run)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{language.strip()}\n{code.rstrip()}\n{fence}"


def inline_code(text: str) -> str:
    if not text:
        return ""
    fence = "``" if "`" in text else "`"
    pad = " " if fence == "``" else ""
    return f"{fence}{pad}{text}{pad}{fence}"


def table(rows: list[list[str]]) -> str:
    """A GFM table; the first row is the header (GFM requires one). Cells are
    flattened to one line, ``|`` escaped, short rows padded."""
    rows = [[_cell(cell) for cell in row] for row in rows if row]
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    lines = [_row(rows[0]), _row(["---"] * width)] + [_row(row) for row in rows[1:]]
    return "\n".join(lines)


def prefix_lines(text: str, first: str, rest: str) -> str:
    """``first`` before the first line and ``rest`` before the others (list
    items, blockquotes); blank lines get ``rest`` without trailing spaces."""
    lines = text.split("\n")
    out = [first + lines[0]]
    out += [(rest + line) if line.strip() else rest.rstrip() for line in lines[1:]]
    return "\n".join(out)


def join_blocks(blocks: list[str]) -> str:
    return "\n\n".join(block for block in (b.strip("\n") for b in blocks) if block.strip())


def tidy(markdown: str) -> str:
    """No trailing spaces, at most one blank line in a row, no blank edges.
    Code blocks are left as they are."""
    out: list[str] = []
    fence: str | None = None
    for line in markdown.split("\n"):
        stripped = line.lstrip()
        if fence is None and stripped.startswith("```"):
            fence = stripped[: len(stripped) - len(stripped.lstrip("`"))]
        elif fence is not None and stripped.startswith(fence) and not stripped.strip("`"):
            fence = None
            out.append(line)
            continue
        if fence is not None:
            out.append(line)
            continue
        line = line.rstrip()
        if not line and (not out or not out[-1]):
            continue
        out.append(line)
    return "\n".join(out).strip("\n")


def _cell(text: str) -> str:
    return " ".join(text.replace("|", "\\|").split())


def _row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"
