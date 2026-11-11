"""«Pubblica su Confluence/Jira» (blocco 10): the draft of a Confluence or
Jira task (``bozza-<task>.md``, saved from Copilot's answer) published with
the project's Atlassian site, only when the user confirms.

- **Target**: the page or issue the task links as a context reference copied
  from Atlassian (``source`` confluence / jira, with its link) is **updated**:
  a page gets the draft's title and body, an issue only its description.
  Otherwise a **new** page (space and parent page) or issue (Jira project and
  issue type) is created; the defaults are the project's.
- **Format**: the draft's Markdown becomes storage format or ADF
  (domain/atlassian/publish_format.py); a ``# title`` on its first line is
  the title (``Bozza: `` dropped).
- **Masking**: aliases (``REPO_1``) go back to the real values before
  publishing; the preview says which.
- **After**: the task is «done» (its items get checked, blocco 08) and the
  page or issue is a context reference linked to the task (a new one is
  copied from Atlassian; the linked one gets the published text).

The preview (``preview``) shows all this, with the target's current text
for the comparison, and changes nothing."""
from core.error import NotFoundError, ValidationError
from domain.atlassian.publish_format import split_title, to_adf, to_storage
from models.domain.note import NoteType, TaskStatus, TaskType
from models.domain.publish import PublishKind, PublishMode, PublishPreview, PublishResult
from service.atlassian_service import _KEY_IN_TEXT, _PAGE_IN_LINK, AtlassianService
from service.copilot_service import output_note_name
from service.masking_service import MaskingService
from service.project_data_service import ProjectDataService

_KINDS = {TaskType.CONFLUENCE: PublishKind.CONFLUENCE, TaskType.JIRA: PublishKind.JIRA}
_DRAFT_PREFIX = "Bozza:"


class PublishService:

    def __init__(self, project_data: ProjectDataService, atlassian: AtlassianService, masking: MaskingService):
        self._data = project_data
        self._atlassian = atlassian
        self._masking = masking

    def preview(self, project_name: str, task_note: str) -> PublishPreview:
        kind, draft, title, body = self._draft(project_name, task_note)
        session = self._masking.session(project_name)
        unmasked = [f"{entry.alias} → {entry.value}" for entry in self._masking.entries(project_name) if entry.alias in f"{title}\n{body}"]
        preview = PublishPreview(kind=kind, mode=PublishMode.CREATE, draft=draft, title=session.unmask(title), body=session.unmask(body),
                                 unmasked=unmasked)
        target = self._target(project_name, task_note, kind)
        site = self._atlassian.site(project_name)
        if target is None:
            return preview.model_copy(update={"space_key": site.confluence_space_key or "", "project_key": site.jira_project_key or ""})
        reference, identifier = target
        if kind is PublishKind.CONFLUENCE:
            page = site.get_page(identifier)
            current = {"target_title": page.title, "target_body": page.body, "target_url": page.url}
        else:
            issue = site.get_issue(identifier)
            current = {"target_title": f"{issue.key} · {issue.summary}", "target_body": issue.description, "target_url": issue.url,
                       "title": issue.summary}
        return preview.model_copy(update={"mode": PublishMode.UPDATE, "reference": reference, **current})

    def publish(self, project_name: str, task_note: str, *, space_key: str = "", parent_id: str = "", project_key: str = "",
                issue_type: str = "") -> PublishResult:
        preview = self.preview(project_name, task_note)
        site = self._atlassian.site(project_name)
        target = self._target(project_name, task_note, preview.kind)
        if preview.kind is PublishKind.CONFLUENCE:
            if target is None:
                page = site.create_page(space_key or None, parent_id or None, preview.title, to_storage(preview.body))
                reference, _ = self._atlassian.reference_from_page(project_name, page.id, [task_note])
            else:
                page = site.update_page(target[1], preview.title, to_storage(preview.body))
                reference = self._refresh(project_name, target[0], preview.body)
            url = page.url
        elif target is None:
            key, url = site.create_issue(project_key or None, issue_type, preview.title, to_adf(preview.body))
            reference, _ = self._atlassian.reference_from_issue(project_name, key, [task_note])
        else:
            url = site.update_issue_description(target[1], to_adf(preview.body))
            reference = self._refresh(project_name, target[0], preview.body)
        task = self._data.agent_task(project_name, task_note)
        if task.status != TaskStatus.DONE:
            self._data.save_agent_task(project_name, task_note, task.model_copy(update={"status": TaskStatus.DONE}))
        return PublishResult(kind=preview.kind, mode=preview.mode, url=url, reference=reference)

    # --------------------------------------------------------------- helpers
    def _draft(self, project_name: str, task_note: str) -> tuple[PublishKind, str, str, str]:
        task = self._data.agent_task(project_name, task_note)
        kind = _KINDS.get(task.type)
        if kind is None:
            raise ValidationError("Si pubblicano solo i task «Doc Confluence» e «Task Jira».")
        draft = output_note_name(task_note, task.type)
        try:
            text = self._data.read_note(project_name, draft)
        except NotFoundError as exc:
            raise NotFoundError(f"Non c'è ancora la bozza {draft}: salva prima la risposta di Copilot come nota.") from exc
        title, body = split_title(text, task.title)
        title = title.removeprefix(_DRAFT_PREFIX).strip() or task.title
        if not body.strip():
            raise ValidationError(f"La bozza {draft} è vuota.")
        return kind, draft, title, body

    def _target(self, project_name: str, task_note: str, kind: PublishKind) -> tuple[str, str] | None:
        """The linked reference copied from a page / issue: (its name, the page id or issue key)."""
        for name in self._data.agent_task(project_name, task_note).references:
            try:
                note_kind, reference = self._data.reference(project_name, name)
            except (NotFoundError, ValidationError):
                continue
            if note_kind != NoteType.CONTEXT_REFERENCE or reference.source != kind.value or not reference.source_url:
                continue
            if kind is PublishKind.CONFLUENCE and (page := _PAGE_IN_LINK.search(reference.source_url)):
                return name, page.group(1) or page.group(2)
            if kind is PublishKind.JIRA and (key := _KEY_IN_TEXT.search(reference.source_url.upper())):
                return name, key.group(0)
        return None

    def _refresh(self, project_name: str, reference_name: str, body: str) -> str:
        _, reference = self._data.reference(project_name, reference_name)
        self._data.save_reference(project_name, reference_name, reference.model_copy(update={"content": body}))
        return reference_name
