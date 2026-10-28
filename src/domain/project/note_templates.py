"""The templates of the typed notes: the markdown written to the note's file
(readable by a person and by an agent) and back. The file may be edited by
hand: parsing is tolerant (unknown lines are ignored, a missing section is
empty), so only what the template knows survives the next save.

Agent task::

    # Refactor del login

    Stato: da fare

    ## Obiettivo
    ...
    ## Contesto
    ...
    ## Criteri di accettazione
    - [ ] I test passano
    - [x] Nessuna API cambiata
    ## Vincoli
    ...
    ## Riferimenti
    - code-reference-login.md

Todo list (priority and due date optional)::

    # Rilascio v2

    - [x] Aggiornare le dipendenze  (alta, 2026-10-30)
    - [ ] Scrivere le note di rilascio  (media)
    - [ ] Taggare il commit
    ## Riferimenti
    - context-reference-procedura-di-rilascio.md

Reference, code or context (repository, file and lines only for code)::

    # Login: controllo della password

    Fonte: jira · https://acme.atlassian.net/browse/NAV-7
    Repository: api
    File: src/auth/login.py
    Righe: 10-40

    ## Contenuto
    ...

``## Riferimenti`` (written only when there are some) links reference notes by name."""
import re
from datetime import date

from models.domain.note import AgentTask, ChecklistItem, Reference, TaskStatus, TodoItem, TodoList, TodoPriority

STATUS_LABELS = {TaskStatus.TODO: "da fare", TaskStatus.IN_PROGRESS: "in corso", TaskStatus.DONE: "fatto"}
PRIORITY_LABELS = {TodoPriority.HIGH: "alta", TodoPriority.MEDIUM: "media", TodoPriority.LOW: "bassa"}

_STATUS = "Stato:"
_SECTIONS = {"objective": "Obiettivo", "context": "Contesto", "criteria": "Criteri di accettazione", "constraints": "Vincoli"}
_REFERENCES = "Riferimenti"
_SOURCE, _SOURCE_SEPARATOR = "Fonte:", " · "
_CODE_FIELDS = {"repository": "Repository:", "path": "File:", "lines": "Righe:"}
_CONTENT = "Contenuto"
_CHECK = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s?(.*)$")
_BULLET = re.compile(r"^\s*[-*]\s+(?!\[[ xX]\])(\S.*?)\s*$")
_DETAILS = re.compile(r"^(.*?)\s+\((?:(alta|media|bassa)(?:,\s*)?)?(\d{4}-\d{2}-\d{2})?\)$", re.IGNORECASE)


# --------------------------------------------------------------- agent task

def render_agent_task(task: AgentTask) -> str:
    lines = [f"# {_line(task.title)}", "", f"{_STATUS} {STATUS_LABELS[task.status]}"]
    for field, heading in _SECTIONS.items():
        lines += ["", f"## {heading}"]
        if field == "criteria":
            lines += [_check(item) for item in task.criteria]
        elif text := getattr(task, field).strip():
            lines.append(text)
    return "\n".join(lines + _references(task.references)) + "\n"


def parse_agent_task(text: str, fallback_title: str) -> AgentTask:
    title, head, sections = _split(text, fallback_title)
    status = next((line[len(_STATUS):].strip().lower() for line in head if line.startswith(_STATUS)), "")
    by_heading = {heading.lower(): field for field, heading in _SECTIONS.items()}
    fields = {by_heading[heading]: body for heading, body in sections.items() if heading in by_heading}
    return AgentTask(
        title=title,
        status=next((key for key, label in STATUS_LABELS.items() if label == status), TaskStatus.TODO),
        objective=_text(fields.get("objective", [])),
        context=_text(fields.get("context", [])),
        criteria=[ChecklistItem(text=text, done=done) for done, text in _checks(fields.get("criteria", []))],
        constraints=_text(fields.get("constraints", [])),
        references=_bullets(sections.get(_REFERENCES.lower(), [])),
    )


# ---------------------------------------------------------------- todo list

def render_todo_list(todo: TodoList) -> str:
    lines = [f"# {_line(todo.title)}", ""]
    for item in todo.items:
        details = [PRIORITY_LABELS[item.priority]] if item.priority else []
        details += [item.due.isoformat()] if item.due else []
        lines.append(_check(item) + (f"  ({', '.join(details)})" if details else ""))
    return "\n".join(lines + _references(todo.references)) + "\n"


def parse_todo_list(text: str, fallback_title: str) -> TodoList:
    title, head, sections = _split(text, fallback_title)
    references = sections.pop(_REFERENCES.lower(), [])
    lines = head + [line for body in sections.values() for line in body]
    return TodoList(title=title, items=[_todo_item(text, done) for done, text in _checks(lines)], references=_bullets(references))


def _todo_item(text: str, done: bool) -> TodoItem:
    match = _DETAILS.match(text)
    if match is None or not (match.group(2) or match.group(3)):
        return TodoItem(text=text, done=done)
    priority = next((key for key, label in PRIORITY_LABELS.items() if label == (match.group(2) or "").lower()), None)
    due = _date(match.group(3))
    return TodoItem(text=match.group(1), done=done, priority=priority, due=due)


# ---------------------------------------------------------------- reference

def render_reference(reference: Reference, code: bool) -> str:
    """``code``: a code reference, with repository, file and lines."""
    lines = [f"# {_line(reference.title)}", ""]
    source = _SOURCE_SEPARATOR.join(part for part in (_line(reference.source), _line(reference.source_url)) if part)
    lines += [f"{_SOURCE} {source}"] if source else []
    if code:
        lines += [f"{label} {_line(getattr(reference, field))}" for field, label in _CODE_FIELDS.items() if getattr(reference, field).strip()]
    lines += ["", f"## {_CONTENT}"] + ([reference.content.strip()] if reference.content.strip() else [])
    return "\n".join(lines) + "\n"


def parse_reference(text: str, fallback_title: str) -> Reference:
    title, head, sections = _split(text, fallback_title)
    values = {field: _value(head, label) for field, label in _CODE_FIELDS.items()}
    source, source_url = _value(head, _SOURCE), ""
    if _SOURCE_SEPARATOR in source:
        source, source_url = (part.strip() for part in source.split(_SOURCE_SEPARATOR, 1))
    elif source.startswith(("http://", "https://")):
        source, source_url = "", source
    return Reference(title=title, source=source, source_url=source_url, content=_text(sections.get(_CONTENT.lower(), [])), **values)


# ------------------------------------------------------------------ helpers

def _split(text: str, fallback_title: str) -> tuple[str, list[str], dict[str, list[str]]]:
    """The ``# title``, the lines before the first ``## section``, and each section's lines by lowercase heading."""
    title, head, sections, current = "", [], {}, None
    for line in text.splitlines():
        if line.startswith("## "):
            current = sections.setdefault(line[3:].strip().lower(), [])
        elif line.startswith("# ") and not title and current is None:
            title = line[2:].strip()
        else:
            (head if current is None else current).append(line)
    return title or fallback_title, head, sections


def _checks(lines: list[str]) -> list[tuple[bool, str]]:
    return [(match.group(1) != " ", match.group(2).strip()) for line in lines if (match := _CHECK.match(line))]


def _check(item: ChecklistItem) -> str:
    return f"- [{'x' if item.done else ' '}] {_line(item.text)}"


def _references(names: list[str]) -> list[str]:
    """The ``## Riferimenti`` section, only when there are some."""
    names = [name for name in (_line(name) for name in names) if name]
    return ["", f"## {_REFERENCES}", *(f"- {name}" for name in names)] if names else []


def _bullets(lines: list[str]) -> list[str]:
    """The ``- item`` lines (not checkboxes), each once, in order."""
    return list(dict.fromkeys(match.group(1) for line in lines if (match := _BULLET.match(line))))


def _value(lines: list[str], label: str) -> str:
    """The text after ``label`` on its line; ``""`` when absent."""
    return next((line[len(label):].strip() for line in lines if line.startswith(label)), "")


def _text(lines: list[str]) -> str:
    return "\n".join(lines).strip()


def _line(text: str) -> str:
    """One line: a newline would break the structure of the file."""
    return " ".join(text.split())


def _date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None
