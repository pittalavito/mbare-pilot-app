"""Evaluations (service/evaluation_service.py): «Elabora WIP» on its data set
with one or more real models, and the context search (RAG) on its data set
with the mock and the real embedder. Launched from resource/scripts or from
the Metriche page (queued for the worker); each one writes a report,
markdown and JSON, in ``<data_home>/evaluations/``."""
from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EvaluationKind(StrEnum):
    WIP = "wip"
    RAG = "rag"


class EvaluationStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class EvaluationRun(BaseModel):
    """An evaluation launched from the page: the worker's queue."""
    id: int | None = None
    kind: EvaluationKind
    models: list[str] = Field(default_factory=list)
    """WIP: the catalog models to compare."""
    embedders: list[str] = Field(default_factory=list)
    """RAG: the embedders to compare (``hashing``, ``openrouter/<model>``)."""
    status: EvaluationStatus = EvaluationStatus.QUEUED
    report: str = ""
    """The report's name once done (``wip-20261110-143000``)."""
    error: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
    finished_at: datetime | None = None


class EvaluationReport(BaseModel):
    """A report on disk: ``<name>.md`` and ``<name>.json``."""
    name: str
    kind: EvaluationKind
    created_at: datetime


class WipCaseResult(BaseModel):
    case: str
    expected: int
    correct: int
    missing: list[str] = Field(default_factory=list)
    """The expected proposals not found, described."""
    extra: list[str] = Field(default_factory=list)
    """The proposals that were not expected, described."""
    error: str | None = None
    latency_ms: float = 0.0


class WipModelResult(BaseModel):
    """One model on the whole WIP data set."""
    model: str
    cases: int
    expected: int
    proposed: int
    correct: int
    precision: float | None
    """Correct over proposed; None without proposals."""
    recall: float | None
    """Correct over expected; None without expected ones."""
    cost_eur: float
    latency_avg_ms: float
    errors: int
    details: list[WipCaseResult]


class RagResult(BaseModel):
    """One embedder, with or without the keyword bonus, on the RAG data set."""
    embedder: str
    bonus: float
    answerable: int
    hit_at_1: float
    hit_at_5: float
    mrr: float
    """Mean of 1/rank of the right section (0 when it is not in the results)."""
    best_score_answerable: float
    """Average best score on the questions with an answer."""
    best_score_unanswerable: float | None
    """Average best score on the questions without one: it should stay well below the one above."""
    misses: list[str] = Field(default_factory=list)
    """The questions whose right section is not in the first 5."""
