"""The Metriche page (cost and latency per agent, Copilot apart, the WIP
acceptance) and the evaluations (WIP with a fake model, RAG with the mock
embedder), their queue for the worker, their reports and the CLI."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from core.error import NotFoundError, ValidationError
from domain.evaluation.scoring import compare, describe, describe_expected, rank, retrieval, similar
from evaluation_cli import main as cli
from fakes import fake_generation, make_run_record
from models.domain.copilot import CopilotPhase, CopilotTurnRecord, CopilotUsage
from models.domain.evaluation import EvaluationKind, EvaluationStatus
from models.domain.wip import ProposalKind, WipAnswer, WipAnswerProposal, WipProposal, WipRun
from service.chat_service import ChatService
from service.evaluation_service import EvaluationService
from service.metrics_service import MetricsService, percentile

MODEL = "openai/gpt-4o"


# ---------------------------------------------------------------- metrics

def test_metrics_group_by_who_with_average_and_p95(run_store, copilot_store, wip_store, project_store):
    now = datetime.now(timezone.utc)
    for index, (name, latency, project, ok) in enumerate([
        ("chatbot/Segretario", 100.0, "acme", True), ("chatbot/Segretario", 300.0, "acme", True), ("chatbot/Segretario", 2000.0, "acme", False),
        ("wip/Segretario", 900.0, "acme", True), ("chatbot/Refiner", 50.0, "beta", True),
    ]):
        record = make_run_record(f"r{index}", created_at=now).model_copy(update={"config_name": name, "latency_ms": latency, "project_name": project, "ok": ok})
        run_store.save(record)
    run_store.save(make_run_record("vecchia", created_at=now - timedelta(days=40)).model_copy(update={"config_name": "chatbot/Segretario"}))
    copilot_store.add_turn(CopilotTurnRecord(session_id=1, project_name="acme", task_note="t.md", phase=CopilotPhase.PLAN, model="gpt-5",
                                             usage=CopilotUsage(premium_requests=1, nano_aiu=200_000_000)))
    service = MetricsService(run_store, copilot_store, wip_store)

    metrics = service.metrics(days=30, project_name="acme")

    by_name = {agent.name: agent for agent in metrics.agents}
    segretario = by_name["chatbot/Segretario"]
    assert (segretario.calls, segretario.errors, segretario.latency_avg_ms, segretario.latency_p95_ms) == (3, 1, 800.0, 2000.0)
    assert segretario.cost_eur == pytest.approx(3 * 0.000825) and segretario.input_tokens == 450 and segretario.models == ["gpt-4o"]
    assert set(by_name) == {"chatbot/Segretario", "wip/Segretario"}  # only acme, only the last 30 days
    assert [item.model for item in metrics.copilot] == ["gpt-5"] and metrics.copilot[0].usage.ai_credits == pytest.approx(0.2)
    assert service.metrics().agents[0].calls == 4  # ever, every project: the old one too
    assert (percentile([], 0.95), percentile([1, 2, 3, 4], 0.5), percentile([5], 0.95)) == (0.0, 2, 5)


def test_wip_acceptance_counts_the_decided_proposals(run_store, copilot_store, wip_store, project_store):
    from models.domain.project import Project, ProjectSource

    project_store.save(Project(name="acme", source=ProjectSource.FOLDER, root_path="/code/acme"))
    now = datetime.now(timezone.utc)
    common = {"project_name": "acme", "model": MODEL, "prompt_version": 1}
    wip_store.save_run(WipRun(run_id="a", proposed=4, applied_at=now, accepted=2, corrected=1, discarded=1, **common))
    wip_store.save_run(WipRun(run_id="b", proposed=2, dismissed_at=now, discarded=2, **common))
    wip_store.save_run(WipRun(run_id="c", proposed=3, **common))  # left open

    wip = MetricsService(run_store, copilot_store, wip_store).metrics().wip

    assert (wip.runs, wip.applied, wip.dismissed, wip.open, wip.proposed) == (3, 1, 1, 1, 9)
    assert (wip.accepted, wip.corrected, wip.discarded, wip.skipped, wip.acceptance_rate) == (2, 1, 3, 0, 0.333)
    assert MetricsService(run_store, copilot_store, wip_store).metrics(days=1, project_name="altro").wip.acceptance_rate is None


# ---------------------------------------------------------------- scoring

def _proposal(kind: ProposalKind, **fields) -> WipProposal:
    return WipProposal(id=1, kind=kind, source="s", **fields)


def test_proposals_are_judged_by_kind_activity_item_and_similar_text():
    assert similar("Note di rilascio", "Scrivere la nota del rilascio") and not similar("Guida di installazione", "Rilascio")
    assert similar("", "qualsiasi")
    expected = [
        {"kind": "new_activity", "title": "Login lento"},
        {"kind": "add_item", "activity_title": "Rilascio v2", "text": "Note di rilascio"},
        {"kind": "check_item", "activity_title": "Rilascio v2", "item": 2},
        {"kind": "set_item", "activity_title": "Demo", "item": 1},
    ]
    proposals = [
        _proposal(ProposalKind.CHECK_ITEM, activity_title="rilascio V2", item=2),
        _proposal(ProposalKind.NEW_ACTIVITY, title="Sistemare il login lento"),
        _proposal(ProposalKind.ADD_ITEM, activity_title="Altra", text="Note di rilascio"),  # wrong activity
        _proposal(ProposalKind.SET_ITEM, activity_title="Demo", item=2),  # wrong item
    ]

    correct, missing, extra = compare(expected, proposals)

    assert correct == 2
    assert [describe_expected(item) for item in missing] == ["add_item: Note di rilascio in «Rilascio v2»", "set_item: voce 1 in «Demo»"]
    assert [describe(item) for item in extra] == ["add_item: Note di rilascio in «Altra»", "set_item: voce 2 in «Demo»"]


def test_ranks_hits_and_mrr():
    results = [("a.md", "Uno"), ("b.md", "Due")]
    assert (rank(results, "b.md", "Due"), rank(results, "c.md", "X")) == (2, None)
    assert retrieval([1, 2, None, 5]) == (0.25, 0.75, 0.425)
    assert retrieval([]) == (0.0, 0.0, 0.0)


# ------------------------------------------------------------ evaluations

class _CaseModel:
    """A fake model that answers some cases of the WIP data set right."""

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.calls = 0

    def structured_response(self, *, input, output_cls, system_prompt=None, **kwargs):
        self.calls += 1
        with fake_generation("gpt-4o", 1000, 100):
            pass
        if self.fail:
            raise RuntimeError("quota finita")
        assert "Giulia Bianchi" not in input  # masked as in the app
        proposals = []
        if "costi cloud" in input:
            proposals.append(WipAnswerProposal(kind="new_activity", source="x", title="Report mensile dei costi del cloud"))
        if "slide della demo" in input:
            proposals.append(WipAnswerProposal(kind="set_item", source="x", activity="attivita-demo-cliente.md", item=1, due="2026-11-13"))
            proposals.append(WipAnswerProposal(kind="new_activity", source="x", title="Inventata"))
        if "riunione lunga" in input:  # an answer without structured data: a failed case
            return SimpleNamespace(structured_data=[])
        return SimpleNamespace(structured_data=[WipAnswer(proposals=proposals)])


@pytest.fixture
def models(monkeypatch):
    by_name = {MODEL: _CaseModel(), "openai/gpt-5.3": _CaseModel(fail=True)}
    chat = ChatService()
    monkeypatch.setattr(chat, "get_client", lambda name: by_name[name])
    return chat, by_name


@pytest.fixture
def evaluations(catalog_store, evaluation_store, config, models, tmp_path) -> EvaluationService:
    return EvaluationService(catalog_store, models[0], evaluation_store, config.eval_data_root, tmp_path / "evaluations")


def test_the_wip_evaluation_compares_models_on_the_data_set(evaluations, models, catalog_store):
    name, [good, failing] = evaluations.run_wip([MODEL, "openai/gpt-5.3", " "])

    assert (good.cases, good.expected, good.proposed, good.correct) == (11, 15, 3, 2)  # the costs report and the demo's due date
    assert (good.precision, good.recall, good.errors) == (0.667, 0.133, 1)
    assert next(d for d in good.details if d.case == "solo-diario").error == "nessuna risposta strutturata"
    assert good.cost_eur > 0 and good.latency_avg_ms >= 0
    demo = next(detail for detail in good.details if detail.case == "scadenze")
    assert (demo.correct, demo.extra) == (1, ["new_activity: Inventata"])
    assert failing.errors == 11 and failing.precision is None and "quota finita" in failing.details[0].error
    report = evaluations.report(name)
    assert report.startswith("# Valutazione di «Elabora WIP»") and f"`{MODEL}`" in report and "quota finita" in report
    assert json.loads(evaluations.report(name, "json"))[0]["model"] == MODEL
    with pytest.raises(ValidationError, match="almeno un modello"):
        evaluations.run_wip([" "])


def test_the_rag_evaluation_reports_hits_with_and_without_the_bonus(evaluations):
    name, results = evaluations.run_rag([])  # hashing by default

    assert [(result.embedder, result.bonus) for result in results] == [("hashing-512", 0.15), ("hashing-512", 0.0)]
    with_bonus, without = results
    assert with_bonus.answerable == 16 and 0 <= with_bonus.hit_at_1 <= with_bonus.hit_at_5 <= 1
    assert with_bonus.best_score_unanswerable is not None and with_bonus.best_score_unanswerable < with_bonus.best_score_answerable
    assert len(with_bonus.misses) == round(16 * (1 - with_bonus.hit_at_5))
    report = evaluations.report(name)
    assert "| `hashing-512` | sì |" in report and "| `hashing-512` | no |" in report
    assert [item.name for item in evaluations.reports()] == [name] and evaluations.reports()[0].kind == EvaluationKind.RAG


def test_unknown_reports_and_empty_data(evaluations, catalog_store, evaluation_store, models, tmp_path):
    for name, extension in (("../segreti", "md"), ("wip-20261110-120000", "md"), ("wip-20261110-120000", "exe")):
        with pytest.raises(NotFoundError):
            evaluations.report(name, extension)
    empty = EvaluationService(catalog_store, models[0], evaluation_store, tmp_path / "vuoto", tmp_path / "evaluations")
    assert empty.reports() == []
    with pytest.raises(ValidationError, match="Nessun caso"):
        empty.run_wip([MODEL])
    (tmp_path / "vuoto" / "rag" / "context").mkdir(parents=True)
    (tmp_path / "vuoto" / "rag" / "questions.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValidationError, match="vuoto"):
        empty.run_rag(["hashing"])


def test_two_reports_in_the_same_second_get_different_names(evaluations):
    first, _ = evaluations.run_rag(["hashing"])
    second, _ = evaluations.run_rag(["hashing"])

    assert first != second and len(evaluations.reports()) == 2


def test_the_worker_runs_the_queued_evaluations(evaluations, models):
    with pytest.raises(ValidationError):
        evaluations.enqueue(EvaluationKind.WIP, [])
    wip = evaluations.enqueue(EvaluationKind.WIP, [MODEL])
    rag = evaluations.enqueue(EvaluationKind.RAG, embedders=[" hashing "])
    broken = evaluations.enqueue(EvaluationKind.RAG, embedders=["sconosciuto"])

    done = evaluations.run_next()
    assert (done.id, done.status, done.report.startswith("wip-")) == (wip.id, EvaluationStatus.DONE, True) and done.finished_at
    assert evaluations.run_next().report.startswith("rag-") and rag.embedders == ["hashing"]
    failed = evaluations.run_next()
    assert (failed.id, failed.status) == (broken.id, EvaluationStatus.FAILED) and "Embedder sconosciuto" in failed.error
    assert evaluations.run_next() is None
    assert [run.status for run in evaluations.runs()] == [EvaluationStatus.FAILED, EvaluationStatus.DONE, EvaluationStatus.DONE]


def test_an_unexpected_crash_fails_the_evaluation_and_the_worker_goes_on(evaluations, monkeypatch):
    evaluations.enqueue(EvaluationKind.RAG)
    monkeypatch.setattr(evaluations, "run_rag", lambda embedders: 1 / 0)

    assert evaluations.run_next().error == "division by zero"


def test_the_cli_runs_an_evaluation_and_prints_the_report(evaluations, capsys):
    assert cli(["rag", "--embedder", "hashing"], service=lambda: evaluations) == 0
    out = capsys.readouterr().out
    assert out.startswith("# Valutazione della ricerca nel contesto") and "Report:" in out

    assert cli(["wip", "--model", "inesistente/x"], service=lambda: evaluations) == 1
    assert "Valutazione non riuscita" in capsys.readouterr().err
