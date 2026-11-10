"""The templates of the typed notes: the markdown written to the note's file
(readable by a person and by an agent) and back. The file may be edited by
hand: parsing is tolerant (unknown lines before the first section are
ignored, a missing section is empty), so only what the template knows
survives the next save.

Only the template's own headings open a section (``## Contesto``, ``##
Contenuto``...): any other ``## `` line, with what follows it, is text of the
section it is in, so markdown with its own headings (a Jira issue, a
Confluence page) stays whole.

Agent task::

    # Refactor del login

    Stato: da fare
    Tipo: sviluppo

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

Activity (status, description, its todo list with optional priority and due
date per item, the agent tasks born from it)::

    # Rilascio v2

    Stato: in corso

    ## Descrizione
    Preparare e pubblicare la 2.0.

    ## Todo
    - [x] Aggiornare le dipendenze  (alta, 2026-10-30)
    - [ ] Scrivere le note di rilascio  (media)
    - [ ] Taggare il commit

    ## Agent task
    - agent-task-note-di-rilascio.md

    ## Imparato
    Le note di rilascio vanno scritte prima del tag.

    ## Riferimenti
    - context-reference-procedura-di-rilascio.md

An old todo list (items right under the title, no status) reads as an activity:
its status is «fatta» when every item is done, else «da fare».

Reference, code or context (repository, file and lines only for code)::

    # Login: controllo della password

    Fonte: jira · https://acme.atlassian.net/browse/NAV-7
    Repository: api
    File: src/auth/login.py
    Righe: 10-40

    ## Contenuto
    ...

``## Riferimenti`` and ``## Agent task`` (written only when there are some)
link notes by name."""
import re
from datetime import date

from models.domain.note import Activity, ActivityStatus, AgentTask, ChecklistItem, Reference, TaskStatus, TaskType, TodoItem, TodoPriority

STATUS_LABELS = {
    TaskStatus.CREATED: "creato", TaskStatus.REFINEMENT: "in rifinitura",
    TaskStatus.TODO: "da fare", TaskStatus.IN_PROGRESS: "in corso", TaskStatus.TO_VERIFY: "da verificare", TaskStatus.DONE: "fatto",
}
TYPE_LABELS = {TaskType.DEVELOPMENT: "sviluppo", TaskType.ANALYSIS: "analisi", TaskType.CONFLUENCE: "doc confluence", TaskType.JIRA: "task jira"}
_OLD_TYPE_LABELS = {"rifinitura": TaskType.JIRA}
"""Labels of types that no longer exist, still read (the file is rewritten only when saved)."""
NOTE_PREFIXES_BY_TYPE = {TaskType.ANALYSIS: "analisi-", TaskType.CONFLUENCE: "bozza-", TaskType.JIRA: "bozza-"}
"""The generic note where Copilot's answer to a plan-only task is saved (``analisi-<task>.md``, ``bozza-<task>.md``)."""
PRIORITY_LABELS = {TodoPriority.HIGH: "alta", TodoPriority.MEDIUM: "media", TodoPriority.LOW: "bassa"}
ACTIVITY_STATUS_LABELS = {ActivityStatus.TODO: "da fare", ActivityStatus.IN_PROGRESS: "in corso", ActivityStatus.DONE: "fatta"}

_STATUS = "Stato:"
_TYPE = "Tipo:"
_SECTIONS = {"objective": "Obiettivo", "context": "Contesto", "criteria": "Criteri di accettazione", "constraints": "Vincoli"}
_REFERENCES = "Riferimenti"
_DESCRIPTION, _TODO, _AGENT_TASKS, _LEARNED = "Descrizione", "Todo", "Agent task", "Imparato"
_SOURCE, _SOURCE_SEPARATOR = "Fonte:", " · "
_CODE_FIELDS = {"repository": "Repository:", "path": "File:", "lines": "Righe:"}
_CONTENT = "Contenuto"
_CHECK = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s?(.*)$")
_BULLET = re.compile(r"^\s*[-*]\s+(?!\[[ xX]\])(\S.*?)\s*$")
_DETAILS = re.compile(r"^(.*?)\s+\((?:(alta|media|bassa)(?:,\s*)?)?(\d{4}-\d{2}-\d{2})?\)$", re.IGNORECASE)


# --------------------------------------------------------------- agent task

def render_agent_task(task: AgentTask) -> str:
    lines = [f"# {_line(task.title)}", "", f"{_STATUS} {STATUS_LABELS[task.status]}", f"{_TYPE} {TYPE_LABELS[task.type]}"]
    for field, heading in _SECTIONS.items():
        lines += ["", f"## {heading}"]
        if field == "criteria":
            lines += [_check(item) for item in task.criteria]
        elif text := getattr(task, field).strip():
            lines.append(text)
    return "\n".join(lines + _references(task.references)) + "\n"


def parse_agent_task(text: str, fallback_title: str) -> AgentTask:
    title, head, sections = _split(text, fallback_title, {*_SECTIONS.values(), _REFERENCES})
    status, kind = (_value(head, label).lower() for label in (_STATUS, _TYPE))
    by_heading = {heading.lower(): field for field, heading in _SECTIONS.items()}
    fields = {by_heading[heading]: body for heading, body in sections.items() if heading in by_heading}
    return AgentTask(
        title=title,
        status=next((key for key, label in STATUS_LABELS.items() if label == status), TaskStatus.CREATED),
        type=next((key for key, label in TYPE_LABELS.items() if label == kind), _OLD_TYPE_LABELS.get(kind, TaskType.DEVELOPMENT)),
        objective=_text(fields.get("objective", [])),
        context=_text(fields.get("context", [])),
        criteria=[ChecklistItem(text=text, done=done) for done, text in _checks(fields.get("criteria", []))],
        constraints=_text(fields.get("constraints", [])),
        references=_bullets(sections.get(_REFERENCES.lower(), [])),
    )


# ----------------------------------------------------------------- activity

def render_activity(activity: Activity) -> str:
    lines = [f"# {_line(activity.title)}", "", f"{_STATUS} {ACTIVITY_STATUS_LABELS[activity.status]}", "", f"## {_DESCRIPTION}"]
    lines += [activity.description.strip()] if activity.description.strip() else []
    lines += ["", f"## {_TODO}"]
    for item in activity.items:
        details = [PRIORITY_LABELS[item.priority]] if item.priority else []
        details += [item.due.isoformat()] if item.due else []
        lines.append(_check(item) + (f"  ({', '.join(details)})" if details else ""))
    lines += _links(_AGENT_TASKS, activity.agent_tasks)
    lines += ["", f"## {_LEARNED}", activity.learned.strip()] if activity.learned.strip() else []
    return "\n".join(lines + _references(activity.references)) + "\n"


def parse_activity(text: str, fallback_title: str) -> Activity:
    title, head, sections = _split(text, fallback_title, {_DESCRIPTION, _TODO, _AGENT_TASKS, _LEARNED, _REFERENCES})
    items = [_todo_item(text, done) for done, text in _checks(head + sections.get(_TODO.lower(), []))]  # head: an old todo list
    label = _value(head, _STATUS).lower()
    status = next((key for key, value in ACTIVITY_STATUS_LABELS.items() if value == label), None)
    if status is None:  # none written (an old todo list) or unknown
        status = ActivityStatus.DONE if items and all(item.done for item in items) else ActivityStatus.TODO
    return Activity(
        title=title,
        status=status,
        description=_text(sections.get(_DESCRIPTION.lower(), [])),
        items=items,
        agent_tasks=_bullets(sections.get(_AGENT_TASKS.lower(), [])),
        references=_bullets(sections.get(_REFERENCES.lower(), [])),
        learned=_text(sections.get(_LEARNED.lower(), [])),
    )


def parse_todo_item(text: str) -> TodoItem:
    """One new item as written in a todo list: ``Taggare il commit  (alta, 2026-10-30)``, not done."""
    return _todo_item(text.strip(), False)


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
    title, head, sections = _split(text, fallback_title, {_CONTENT})
    values = {field: _value(head, label) for field, label in _CODE_FIELDS.items()}
    source, source_url = _value(head, _SOURCE), ""
    if _SOURCE_SEPARATOR in source:
        source, source_url = (part.strip() for part in source.split(_SOURCE_SEPARATOR, 1))
    elif source.startswith(("http://", "https://")):
        source, source_url = "", source
    return Reference(title=title, source=source, source_url=source_url, content=_text(sections.get(_CONTENT.lower(), [])), **values)


# ------------------------------------------------------------------ helpers

def _split(text: str, fallback_title: str, headings: set[str]) -> tuple[str, list[str], dict[str, list[str]]]:
    """The ``# title``, the lines before the first section, and each section's
    lines by lowercase heading. Only ``headings`` (the template's) open a
    section: another ``## `` line stays in the lines of the current one."""
    known = {heading.lower() for heading in headings}
    title, head, sections, current = "", [], {}, None
    for line in text.splitlines():
        if line.startswith("## ") and line[3:].strip().lower() in known:
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
    return _links(_REFERENCES, names)


def _links(heading: str, names: list[str]) -> list[str]:
    """A section of note names (``- name``), only when there are some."""
    names = [name for name in (_line(name) for name in names) if name]
    return ["", f"## {heading}", *(f"- {name}" for name in names)] if names else []


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
