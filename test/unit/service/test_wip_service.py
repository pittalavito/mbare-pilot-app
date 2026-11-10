"""«Elabora WIP» with a fake model: the preview masks everything the model
gets, one structured call gives proposals in clear, applying them needs no
LLM and puts the sign in the note."""
import json
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.error import ConflictError, NotFoundError, UpstreamError, ValidationError
from domain.chat.chatbots_default import DEFAULT_WIP_PROMPT
from fakes import FakeStructuredClient as FakeClient
from models.domain.chatbot import Chatbot, ChatbotKind
from models.domain.masking import MaskCategory
from models.domain.note import Activity, TodoItem, TodoPriority
from models.domain.project import Project, ProjectSource
from models.domain.wip import ProposalKind, WipAnswer, WipAnswerProposal, WipChoice
from service.chat_service import ChatService
from service.wip_service import WipService

TODAY = date(2026, 11, 10)
NOW = datetime(2026, 11, 10, 14, 30)
DATA = Path(__file__).parents[3] / "resource" / "eval" / "wip"
MODEL = "openai/gpt-4o"


@pytest.fixture
def client():
    return FakeClient()


@pytest.fixture
def service(project_store, project_data_service, masking_service, chatbot_store, catalog_store, run_store, stores, client, monkeypatch):
    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path="/code/acme"))
    chatbot_store.save_chatbot(Chatbot(project_name="acme", name="Segretario", kind=ChatbotKind.SECRETARY, system_prompt="Sei il segretario.",
                                       model=MODEL))
    chat = ChatService()
    monkeypatch.setattr(chat, "get_client", lambda model: client)
    return WipService(project_data_service, masking_service, chatbot_store, chat, catalog_store, run_store, stores.wip)


@pytest.fixture
def data(project_data_service):
    return project_data_service


def _write(data, text: str) -> None:
    data.save_note("acme", "wip.md", text)


def _release(data) -> str:
    return data.create_activity("acme", Activity(title="Rilascio v2", items=[
        TodoItem(text="Aggiornare le dipendenze", done=True), TodoItem(text="Taggare il commit"), TodoItem(text="Scrivere le note"),
    ]))


def _proposal(kind: ProposalKind, **fields) -> WipAnswerProposal:
    return WipAnswerProposal(kind=kind, source=fields.pop("source", "dal testo"), **fields)


# ------------------------------------------------------------------ state

def test_a_missing_wip_is_empty_and_has_nothing_to_process(service):
    assert service.state("acme").model_dump() == {"content": "", "pending_words": 0}
    with pytest.raises(ValidationError, match="Niente da elaborare"):
        service.preview("acme")
    with pytest.raises(ValidationError, match="Niente da elaborare"):
        service.process("acme")


def test_the_state_counts_only_the_new_text(service, data):
    _write(data, "vecchio diario lungo\n\n—— elaborato il 01/11 09:00 ——\n\ntre parole nuove")

    assert service.state("acme").pending_words == 3


# ---------------------------------------------------------------- preview

def test_the_preview_is_the_whole_input_masked_and_tags_enter_the_map(service, data, masking_service):
    masking_service.add_term("acme", MaskCategory.PERSON, "Marco")
    _release(data)
    data.create_activity("acme", Activity(title="Chiusa", status="done"))
    _write(data, "il tag l'ho fatto, chiedere a Marco e a mask{Acme Spa}.\n\nscrivere a ada@acme.it")

    preview = service.preview("acme", today=TODAY)

    assert preview.text.startswith("Oggi: 2026-11-10 (martedì)\n\nAttività aperte:\n- attivita-rilascio-v2.md · Rilascio v2\n"
                                   "  2. Taggare il commit\n  3. Scrivere le note\n\nTesto nuovo della WIP:\n")
    assert "Chiusa" not in preview.text  # only the open activities
    assert preview.text.endswith("il tag l'ho fatto, chiedere a PERSONA_1 e a TERMINE_1.\n\nscrivere a MAIL_1")
    assert [(span.alias, span.origin.value) for span in preview.spans] == [("PERSONA_1", "map"), ("TERMINE_1", "tag"), ("MAIL_1", "auto")]
    assert (preview.words, preview.paragraphs, preview.processing, preview.over_limit) == (14, 2, 2, False)
    assert [entry.value for entry in masking_service.entries("acme")] == ["Marco", "Acme Spa"]  # the tag stays hidden next time, the email not


def test_a_long_wip_can_be_processed_a_few_paragraphs_at_a_time(service, data):
    _write(data, "\n\n".join(" ".join(["parola"] * 700) for _ in range(3)))

    preview = service.preview("acme", paragraphs=1, today=TODAY)

    assert (preview.paragraphs, preview.processing, preview.words, preview.over_limit) == (3, 1, 700, True)


def test_a_tag_too_short_is_an_error(service, data):
    _write(data, "sentire mask{Al}")

    with pytest.raises(ValidationError, match="almeno 3 caratteri: Al"):
        service.preview("acme")


def test_without_a_secretary_nothing_is_processed(service, data, chatbot_store):
    _write(data, "qualcosa")
    for bot in chatbot_store.list_chatbots("acme"):
        chatbot_store.delete_chatbot(bot.id)

    with pytest.raises(ValidationError, match="Nessun segretario"):
        service.process("acme")


# ---------------------------------------------------------------- process

def test_one_call_gives_the_proposals_in_clear_and_drops_those_not_in_the_list(service, data, client, masking_service, run_store, stores):
    masking_service.add_term("acme", MaskCategory.PERSON, "Marco")
    release = _release(data)
    _write(data, "il tag della 2.0 fatto. note entro venerdì, sentire Marco. scrivere a ada@acme.it")
    client.answer = WipAnswer(proposals=[
        _proposal(ProposalKind.CHECK_ITEM, activity=release, item=2, source="il tag della 2.0 fatto."),
        _proposal(ProposalKind.SET_ITEM, activity=release, item=3, due=date(2026, 11, 13), source="note entro venerdì"),
        _proposal(ProposalKind.NEW_ACTIVITY, title="Log da PERSONA_1", description="Chiedere i log", items=["Scrivere a MAIL_1", " "]),
        _proposal(ProposalKind.ADD_ITEM, activity=release, text="Sentire PERSONA_1", priority="high"),
        _proposal(ProposalKind.CHECK_ITEM, activity=release, item=1),  # done already: not in the list
        _proposal(ProposalKind.CHECK_ITEM, activity="attivita-inventata.md", item=1),
        _proposal(ProposalKind.SET_ITEM, activity=release, item=2),  # nothing to set
        _proposal(ProposalKind.NEW_ACTIVITY, title=" "),
        _proposal(ProposalKind.ADD_ITEM, activity=release, text=""),
    ])

    result = service.process("acme", today=TODAY)

    sent = client.calls[0]
    assert sent["system_prompt"] == DEFAULT_WIP_PROMPT and sent["output_cls"] is WipAnswer
    assert "Marco" not in sent["input"] and "ada@acme.it" not in sent["input"] and "PERSONA_1" in sent["input"]
    assert [(p.id, p.kind.value) for p in result.proposals] == [(1, "check_item"), (2, "set_item"), (3, "new_activity"), (4, "add_item")]
    check, due, new, add = result.proposals
    assert (check.activity_title, check.item_text, check.source) == ("Rilascio v2", "Taggare il commit", "il tag della 2.0 fatto.")
    assert (due.item_text, due.due) == ("Scrivere le note", date(2026, 11, 13))
    assert (new.title, new.items) == ("Log da Marco", ["Scrivere a ada@acme.it"])  # back in clear, the temporary alias too
    assert (add.text, add.priority.value) == ("Sentire Marco", "high")

    [summary] = run_store.list_runs()
    assert (summary.run_id, summary.origin, summary.config_name, summary.ok) == (result.run_id, "wip", "wip/Segretario", True)
    assert summary.total_tokens.input_tokens == 300
    trace = run_store.get_trace(result.run_id)
    assert "Marco" in trace.input and "Sentire Marco" in trace.output  # the record keeps the real values
    run = stores.wip.get_run(result.run_id)
    assert (run.proposed, run.prompt_version, run.model, run.applied_at) == (4, 1, MODEL, None)


def test_the_secretary_s_own_prompt_is_used_when_written(service, data, client, chatbot_store):
    [secretary] = chatbot_store.list_chatbots("acme")
    chatbot_store.save_chatbot(secretary.model_copy(update={"wip_prompt": "Solo attività nuove.", "wip_prompt_version": 3}))
    _write(data, "qualcosa da fare")

    result = service.process("acme")

    assert client.calls[0]["system_prompt"] == "Solo attività nuove."
    assert service.runs("acme")[0].run_id == result.run_id and service.runs("acme")[0].prompt_version == 3


def test_a_failed_call_is_recorded_and_reported(service, data, client, run_store, stores):
    _write(data, "qualcosa da fare")
    client.error = RuntimeError("quota finita")

    with pytest.raises(UpstreamError, match="Il segretario non ha risposto: quota finita"):
        service.process("acme")

    [summary] = run_store.list_runs()
    assert (summary.origin, summary.ok) == ("wip", False)
    assert service.runs("acme") == []  # nothing to apply


def test_an_answer_without_structured_data_is_a_failure(service, data, client, monkeypatch):
    _write(data, "qualcosa da fare")
    monkeypatch.setattr(client, "structured_response", lambda **kwargs: SimpleNamespace(structured_data=[]))

    with pytest.raises(UpstreamError, match="nessuna risposta strutturata"):
        service.process("acme")


# ------------------------------------------------------------------ apply

def test_applying_does_what_was_chosen_and_signs_the_note(service, data, client, stores):
    release = _release(data)
    _write(data, "diario\n\n—— elaborato il 01/11 09:00 ——\n\nil tag è fatto\n\nnote entro venerdì\n\naltro dopo")
    client.answer = WipAnswer(proposals=[
        _proposal(ProposalKind.CHECK_ITEM, activity=release, item=2),
        _proposal(ProposalKind.SET_ITEM, activity=release, item=3, priority="medium", due=date(2026, 11, 13)),
        _proposal(ProposalKind.ADD_ITEM, activity=release, text="Annunciare", priority="low"),
        _proposal(ProposalKind.NEW_ACTIVITY, title="Login lento", description="È lento", items=["Analizzare"]),
        _proposal(ProposalKind.NEW_ACTIVITY, title="Scartata"),
    ])
    result = service.process("acme", paragraphs=2)
    check, due, add, new, _ = result.proposals
    new = new.model_copy(update={"title": "Login troppo lento"})

    applied = service.apply("acme", result.run_id, [WipChoice(proposal=check), WipChoice(proposal=due), WipChoice(proposal=add),
                                                     WipChoice(proposal=new, edited=True)], now=NOW)

    assert applied.skipped == [] and applied.applied == [
        "Spuntata «Taggare il commit» in «Rilascio v2»",
        "«Scrivere le note» in «Rilascio v2»: priorità medium, scadenza 2026-11-13",
        "Voce «Annunciare» aggiunta a «Rilascio v2»",
        "Nuova attività «Login troppo lento» (attivita-login-troppo-lento.md)",
    ]
    items = data.activity("acme", release).items
    assert [(item.text, item.done, item.priority, item.due) for item in items] == [
        ("Aggiornare le dipendenze", True, None, None), ("Taggare il commit", True, None, None),
        ("Scrivere le note", False, TodoPriority.MEDIUM, date(2026, 11, 13)), ("Annunciare", False, TodoPriority.LOW, None),
    ]
    created = data.activity("acme", "attivita-login-troppo-lento.md")
    assert (created.description, [item.text for item in created.items]) == ("È lento", ["Analizzare"])
    assert data.read_note("acme", "wip.md") == (
        "diario\n\n—— elaborato il 01/11 09:00 ——\n\nil tag è fatto\n\nnote entro venerdì\n\n—— elaborato il 10/11 14:30 ——\n\naltro dopo\n"
    )
    run = stores.wip.get_run(result.run_id)
    assert (run.accepted, run.corrected, run.discarded, run.skipped) == (3, 1, 1, 0) and run.applied_at is not None

    with pytest.raises(ConflictError, match="già state applicate"):
        service.apply("acme", result.run_id, [WipChoice(proposal=check)])


def test_proposals_on_what_changed_meanwhile_are_skipped(service, data, client, stores):
    release = _release(data)
    data.create_activity("acme", Activity(title="Da cancellare", items=[TodoItem(text="Voce")]))
    _write(data, "testo")
    client.answer = WipAnswer(proposals=[
        _proposal(ProposalKind.CHECK_ITEM, activity=release, item=2),
        _proposal(ProposalKind.SET_ITEM, activity=release, item=3, priority="high"),
        _proposal(ProposalKind.ADD_ITEM, activity="attivita-da-cancellare.md", text="Nuova"),
        _proposal(ProposalKind.NEW_ACTIVITY, title="Rilascio v2"),  # the name is taken
    ])
    result = service.process("acme")
    activity = data.activity("acme", release)
    activity.items[1].done = True  # ticked by hand meanwhile
    activity.items[2].text = "Scrivere le note di rilascio"  # changed
    data.save_activity("acme", release, activity)
    data.delete_note("acme", "attivita-da-cancellare.md")

    applied = service.apply("acme", result.run_id, [WipChoice(proposal=proposal) for proposal in result.proposals])

    assert applied.applied == []
    assert [line.split(":")[0] for line in applied.skipped] == [
        "Voce 2 di «Rilascio v2»", "Voce 3 di «Rilascio v2»", "Voce «Nuova»", "Nuova attività «Rilascio v2»",
    ]
    assert "già fatta" in applied.skipped[0] and "cambiata" in applied.skipped[1]
    assert stores.wip.get_run(result.run_id).skipped == 4
    assert "—— elaborato il" in data.read_note("acme", "wip.md")  # processed anyway


def test_edited_proposals_that_became_empty_are_skipped(service, data, client):
    release = _release(data)
    _write(data, "testo")
    client.answer = WipAnswer(proposals=[
        _proposal(ProposalKind.NEW_ACTIVITY, title="Qualcosa"),
        _proposal(ProposalKind.ADD_ITEM, activity=release, text="Voce"),
        _proposal(ProposalKind.SET_ITEM, activity=release, item=3, priority="high"),
    ])
    result = service.process("acme")
    emptied = [result.proposals[0].model_copy(update={"title": " "}), result.proposals[1].model_copy(update={"text": ""}),
               result.proposals[2].model_copy(update={"priority": None})]

    applied = service.apply("acme", result.run_id, [WipChoice(proposal=proposal, edited=True) for proposal in emptied])

    assert [line.split(": ")[1] for line in applied.skipped] == ["manca il titolo", "la voce è vuota", "niente da cambiare"]


def test_nothing_chosen_a_changed_wip_or_an_unknown_run(service, data, client):
    _write(data, "primo\n\nsecondo")
    client.answer = WipAnswer(proposals=[_proposal(ProposalKind.NEW_ACTIVITY, title="Qualcosa")])
    result = service.process("acme")

    with pytest.raises(ValidationError, match="Nessuna proposta scelta"):
        service.apply("acme", result.run_id, [])
    with pytest.raises(NotFoundError):
        service.apply("acme", "inventato", [WipChoice(proposal=result.proposals[0])])
    _write(data, "primo riscritto\n\nsecondo")
    with pytest.raises(ConflictError, match="La WIP è cambiata"):
        service.apply("acme", result.run_id, [WipChoice(proposal=result.proposals[0])])
    assert data.activities("acme") == []  # nothing done


def test_dismissing_counts_every_proposal_as_discarded_and_leaves_the_wip_to_process(service, data, client, stores):
    _write(data, "primo")
    client.answer = WipAnswer(proposals=[_proposal(ProposalKind.NEW_ACTIVITY, title="Una"), _proposal(ProposalKind.NEW_ACTIVITY, title="Due")])
    result = service.process("acme")

    dismissed = service.dismiss("acme", result.run_id)

    assert (dismissed.discarded, dismissed.accepted, dismissed.applied_at) == (2, 0, None) and dismissed.dismissed_at is not None
    assert stores.wip.get_run(result.run_id).dismissed_at is not None
    assert data.read_note("acme", "wip.md") == "primo" and data.activities("acme") == []  # no sign, nothing done
    with pytest.raises(ConflictError, match="annullate"):
        service.dismiss("acme", result.run_id)
    with pytest.raises(ConflictError, match="annullate"):
        service.apply("acme", result.run_id, [WipChoice(proposal=result.proposals[0])])

    applied = service.process("acme")
    service.apply("acme", applied.run_id, [WipChoice(proposal=applied.proposals[0])])
    with pytest.raises(ConflictError, match="già state applicate"):
        service.dismiss("acme", applied.run_id)
    with pytest.raises(NotFoundError):
        service.dismiss("altro", applied.run_id)


# ------------------------------------------------------------ the data set

@pytest.mark.parametrize("case", sorted(DATA.glob("*.json")), ids=lambda path: path.stem)
def test_no_sensitive_value_of_the_data_set_reaches_the_model(case, service, data, client, masking_service):
    spec = json.loads(case.read_text(encoding="utf-8"))
    for entry in spec["map"]:
        masking_service.add_term("acme", MaskCategory(entry["category"]), entry["value"])
    for activity in spec["activities"]:
        data.create_activity("acme", Activity(title=activity["title"], items=[TodoItem(**item) for item in activity["items"]]))
    _write(data, spec["wip"])

    preview = service.preview("acme", today=TODAY)
    service.process("acme", today=TODAY)

    sent = client.calls[0]["input"]
    assert sent == preview.text  # what the preview showed is what the model got
    for value in spec["sensitive"]:
        assert value.lower() not in sent.lower(), f"{value} è arrivato al modello"
    assert {item["kind"] for item in spec["expected"]} <= set(ProposalKind)  # the expected proposals are valid kinds
