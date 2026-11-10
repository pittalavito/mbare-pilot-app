"""Evaluations with the numbers at hand (the Metriche page, resource/scripts):

- **WIP** (``run_wip``): every case of ``resource/eval/wip/`` through the same
  path as «Elabora WIP» (input built by ``model_input``, masked, one
  structured call, proposals by ``to_proposals``) with each chosen model; the
  proposals are judged by rules (domain/evaluation/scoring.py): right,
  missing, extra, precision and recall, with cost (catalog prices) and
  latency.
- **RAG** (``run_rag``): the context of ``resource/eval/rag/`` split and
  embedded in memory (as RagService does, nothing stored) with each chosen
  embedder; every question searched with and without the keyword bonus:
  hit@1, hit@5 and MRR on the questions with an answer, the best score on
  those without (it should stay low).

Each evaluation writes ``<name>.md`` (for a person, the speech) and
``<name>.json`` in ``<data_home>/evaluations/``. From the page an evaluation
is queued (``enqueue``) and the worker runs it (``run_next``); the scripts
call ``run_wip`` / ``run_rag`` directly. They are not in the automated tests:
they cost. The tests run them with a fake model and the mock embedder."""
import json
import re
from collections.abc import Callable
from datetime import date, datetime, timezone
from pathlib import Path
from time import perf_counter

from datapizza.tracing import ContextTracing

from core.error import AppError, NotFoundError, ValidationError
from core.observability import LogPrefix, log_exception, observed
from domain.agent.tracing import Adapter as TracingAdapter
from domain.chat.chatbots_default import DEFAULT_WIP_PROMPT
from domain.client.embedding.embedder import Embedder, Factory
from domain.evaluation.scoring import compare, describe, describe_expected, rank, retrieval
from domain.masking.preview import masked_text, tagged_terms
from domain.project.data_paths import typed_note_file_name
from domain.rag.chunking import split_markdown, title_of
from models.domain.evaluation import (
    EvaluationKind,
    EvaluationReport,
    EvaluationRun,
    EvaluationStatus,
    RagResult,
    WipCaseResult,
    WipModelResult,
)
from models.domain.masking import MaskCategory, MaskEntry
from models.domain.note import Activity, NoteType, TodoItem
from models.domain.wip import WipAnswer
from service.chat_service import ChatService
from service.model_service import require_usable_model
from service.rag_service import KEYWORD_BONUS, keywords, score
from service.store.catalog_store import CatalogStore
from service.store.evaluation_store import EvaluationStore
from service.wip_service import Listing, model_input, to_proposals

DEFAULT_TODAY = date(2026, 11, 10)
_REPORT = re.compile(r"^(wip|rag)-\d{8}-\d{6}(-\d+)?$")


class EvaluationService:

    def __init__(self, catalog: CatalogStore, chat: ChatService, evaluations: EvaluationStore, data_root: Path, reports_root: Path,
                 embedders: Callable[[str], Embedder] = Factory.create):
        """``data_root``: the data sets (``resource/eval``); ``reports_root``:
        where reports go; ``embedders``: builds an embedder by name (tests: the mock)."""
        self._catalog = catalog
        self._chat = chat
        self._evaluations = evaluations
        self._data = data_root
        self._reports = reports_root
        self._embedders = embedders

    # ------------------------------------------------------------------- WIP
    @observed(LogPrefix.EVALUATION_SERVICE)
    def run_wip(self, models: list[str], prompt: str = "") -> tuple[str, list[WipModelResult]]:
        """Every case with every model; the report's name and the results.
        ``prompt``: the instructions (``""`` = the default secretary's)."""
        models = [model.strip() for model in models if model.strip()]
        if not models:
            raise ValidationError("Scegli almeno un modello da valutare.")
        for model in models:
            require_usable_model(self._catalog, model)
        cases = sorted((self._data / "wip").glob("*.json"))
        if not cases:
            raise ValidationError(f"Nessun caso in {self._data / 'wip'}.")
        results = [self._wip_model(model, cases, prompt or DEFAULT_WIP_PROMPT) for model in models]
        name = self._write(EvaluationKind.WIP, _wip_markdown(results), [result.model_dump(mode="json") for result in results])
        return name, results

    def _wip_model(self, model: str, cases: list[Path], prompt: str) -> WipModelResult:
        client = self._chat.get_client(model)
        prices = self._catalog.price_list()
        details, cost, proposed = [], 0.0, 0
        for path in cases:
            spec = json.loads(path.read_text(encoding="utf-8"))
            entries, tagged = _entries(spec)
            activities = [(typed_note_file_name(NoteType.ACTIVITY, item["title"]),
                           Activity(title=item["title"], items=[TodoItem(**todo) for todo in item.get("items", [])]))
                          for item in spec.get("activities", [])]
            listing = Listing(activities)
            today = date.fromisoformat(spec["today"]) if spec.get("today") else DEFAULT_TODAY
            masked = masked_text(model_input(today, listing, spec["wip"]), entries, tagged)
            start = perf_counter()
            with ContextTracing().trace(f"eval.wip.{path.stem}") as current_trace:
                try:
                    response = client.structured_response(input=masked.text, output_cls=WipAnswer, system_prompt=prompt)
                    if not response.structured_data:
                        raise ValueError("nessuna risposta strutturata")
                    data = response.structured_data[0]
                    answer = WipAnswer.model_validate(data.model_dump() if hasattr(data, "model_dump") else data)
                    error = None
                except Exception as exc:  # noqa: BLE001 - a failed case is counted, the evaluation goes on
                    answer, error = WipAnswer(proposals=[]), str(exc) or type(exc).__name__
                cost += TracingAdapter.to_run_telemetry(current_trace.get_spans(), prices).total_tokens.cost_eur
            latency = round((perf_counter() - start) * 1000, 1)
            proposals = to_proposals(answer, listing, entries, masked.temporary)
            proposed += len(proposals)
            correct, missing, extra = compare(spec.get("expected", []), proposals)
            details.append(WipCaseResult(case=path.stem, expected=len(spec.get("expected", [])), correct=correct, error=error,
                                         missing=[describe_expected(item) for item in missing], extra=[describe(item) for item in extra],
                                         latency_ms=latency))
        expected = sum(item.expected for item in details)
        correct = sum(item.correct for item in details)
        return WipModelResult(
            model=model, cases=len(details), expected=expected, proposed=proposed, correct=correct,
            precision=round(correct / proposed, 3) if proposed else None, recall=round(correct / expected, 3) if expected else None,
            cost_eur=round(cost, 6), latency_avg_ms=round(sum(item.latency_ms for item in details) / len(details), 1),
            errors=sum(item.error is not None for item in details), details=details,
        )

    # ------------------------------------------------------------------- RAG
    @observed(LogPrefix.EVALUATION_SERVICE)
    def run_rag(self, embedders: list[str]) -> tuple[str, list[RagResult]]:
        """Every question with every embedder, with and without the keyword bonus."""
        names = [name.strip() for name in embedders if name.strip()] or ["hashing"]
        documents = sorted((self._data / "rag" / "context").glob("*.md"))
        questions = json.loads((self._data / "rag" / "questions.json").read_text(encoding="utf-8"))
        if not documents or not questions:
            raise ValidationError(f"Set del RAG vuoto in {self._data / 'rag'}.")
        results = []
        for name in names:
            embedder = self._embedders(name)
            pieces = []
            for path in documents:
                text = path.read_text(encoding="utf-8")
                title = title_of(text, path.stem)
                for chunk in split_markdown(text, title):
                    section = str(chunk.metadata["section"])
                    content = f"{title} {section} {chunk.text}"
                    pieces.append((f"context/{path.name}", section, content, embedder.embed(f"{title}\n{section}\n{chunk.text}")))
            queries = [(item, embedder.embed(item["question"]), keywords(item["question"])) for item in questions]
            for bonus in (KEYWORD_BONUS, 0.0):
                results.append(_rag_result(embedder.name, bonus, pieces, queries))
        report = self._write(EvaluationKind.RAG, _rag_markdown(results, len(questions)), [result.model_dump(mode="json") for result in results])
        return report, results

    # ---------------------------------------------------------------- queue
    def enqueue(self, kind: EvaluationKind, models: list[str] | None = None, embedders: list[str] | None = None) -> EvaluationRun:
        """An evaluation for the worker; the models are checked now."""
        models = [model.strip() for model in models or [] if model.strip()]
        if kind == EvaluationKind.WIP:
            if not models:
                raise ValidationError("Scegli almeno un modello da valutare.")
            for model in models:
                require_usable_model(self._catalog, model)
        return self._evaluations.save_run(EvaluationRun(kind=kind, models=models, embedders=[name.strip() for name in embedders or [] if name.strip()]))

    def runs(self) -> list[EvaluationRun]:
        """The last ones, newest first."""
        return self._evaluations.list_runs()

    def run_next(self) -> EvaluationRun | None:
        """The worker: the oldest queued evaluation, run now; None when there is none."""
        run = self._evaluations.claim_next()
        if run is None:
            return None
        try:
            name = self.run_wip(run.models)[0] if run.kind == EvaluationKind.WIP else self.run_rag(run.embedders)[0]
            update = {"status": EvaluationStatus.DONE, "report": name}
        except AppError as exc:
            update = {"status": EvaluationStatus.FAILED, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001 - the worker goes on
            log_exception(LogPrefix.EVALUATION_SERVICE, "Valutazione %s non riuscita", run.id)
            update = {"status": EvaluationStatus.FAILED, "error": str(exc) or type(exc).__name__}
        return self._evaluations.save_run(run.model_copy(update={**update, "finished_at": datetime.now(timezone.utc)}))

    # --------------------------------------------------------------- reports
    def reports(self) -> list[EvaluationReport]:
        """The reports on disk, newest first."""
        if not self._reports.is_dir():
            return []
        found = [path for path in self._reports.glob("*.md") if _REPORT.match(path.stem)]
        return [EvaluationReport(name=path.stem, kind=EvaluationKind(path.stem.split("-", 1)[0]),
                                 created_at=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc))
                for path in sorted(found, key=lambda path: path.stem, reverse=True)]

    def report(self, name: str, extension: str = "md") -> str:
        """A report's markdown (``md``) or JSON (``json``); NotFoundError for an unknown name."""
        if not _REPORT.match(name) or extension not in ("md", "json"):
            raise NotFoundError(f"Report non trovato: {name}")
        path = self._reports / f"{name}.{extension}"
        if not path.is_file():
            raise NotFoundError(f"Report non trovato: {name}")
        return path.read_text(encoding="utf-8")

    def _write(self, kind: EvaluationKind, markdown: str, data: list[dict]) -> str:
        self._reports.mkdir(parents=True, exist_ok=True)
        name = f"{kind.value}-{datetime.now():%Y%m%d-%H%M%S}"
        suffix = 1
        while (self._reports / f"{name}.md").exists():  # two in the same second
            suffix += 1
            name = f"{kind.value}-{datetime.now():%Y%m%d-%H%M%S}-{suffix}"
        (self._reports / f"{name}.md").write_text(markdown, encoding="utf-8")
        (self._reports / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return name


def _entries(spec: dict) -> tuple[list[MaskEntry], list[str]]:
    """A case's masking map (its ``map`` plus its ``mask{}`` terms), aliases numbered per category."""
    tagged = tagged_terms(spec["wip"])
    counters: dict[MaskCategory, int] = {}
    entries = []
    for category, value in [(MaskCategory(item["category"]), item["value"]) for item in spec.get("map", [])] + \
                           [(MaskCategory.TERM, term) for term in tagged]:
        counters[category] = counters.get(category, 0) + 1
        entries.append(MaskEntry(category=category, value=value, alias=f"{category.alias_prefix}_{counters[category]}"))
    return entries, tagged


def _rag_result(embedder: str, bonus: float, pieces: list[tuple[str, str, str, list[float]]],
                queries: list[tuple[dict, list[float], set[str]]]) -> RagResult:
    ranks, best_answerable, best_unanswerable, misses = [], [], [], []
    for item, vector, words in queries:
        scored = sorted(((score(vector, words, content, embedding, bonus), path, section) for path, section, content, embedding in pieces),
                        reverse=True)
        best = scored[0][0] if scored else 0.0
        if item.get("path") is None:
            best_unanswerable.append(best)
            continue
        position = rank([(path, section) for _, path, section in scored[:5]], item["path"], item["section"])
        ranks.append(position)
        best_answerable.append(best)
        if position is None:
            misses.append(item["question"])
    hit1, hit5, mrr = retrieval(ranks)
    return RagResult(
        embedder=embedder, bonus=bonus, answerable=len(ranks), hit_at_1=hit1, hit_at_5=hit5, mrr=mrr,
        best_score_answerable=round(sum(best_answerable) / len(best_answerable), 3) if best_answerable else 0.0,
        best_score_unanswerable=round(sum(best_unanswerable) / len(best_unanswerable), 3) if best_unanswerable else None, misses=misses,
    )


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.0f}%"


def _wip_markdown(results: list[WipModelResult]) -> str:
    lines = [f"# Valutazione di «Elabora WIP» · {datetime.now():%d/%m/%Y %H:%M}", "",
             f"{results[0].cases} casi del set `resource/eval/wip/`; una proposta è giusta con lo stesso tipo, la stessa attività e la "
             "stessa voce o un testo simile (regole nel codice).", "",
             "| Modello | Giuste | Attese | Proposte | Precisione | Richiamo | Costo | Latenza media | Errori |",
             "|---|---|---|---|---|---|---|---|---|"]
    lines += [f"| `{r.model}` | {r.correct} | {r.expected} | {r.proposed} | {_percent(r.precision)} | {_percent(r.recall)} | "
              f"€ {r.cost_eur:.4f} | {r.latency_avg_ms / 1000:.1f} s | {r.errors} |" for r in results]
    for result in results:
        lines += ["", f"## `{result.model}`", "", "| Caso | Giuste/Attese | Mancanti | In più | Errore |", "|---|---|---|---|---|"]
        lines += [f"| {d.case} | {d.correct}/{d.expected} | {'; '.join(d.missing) or '—'} | {'; '.join(d.extra) or '—'} | {d.error or '—'} |"
                  for d in result.details]
    return "\n".join(lines) + "\n"


def _rag_markdown(results: list[RagResult], questions: int) -> str:
    lines = [f"# Valutazione della ricerca nel contesto (RAG) · {datetime.now():%d/%m/%Y %H:%M}", "",
             f"{questions} domande del set `resource/eval/rag/` ({results[0].answerable} con risposta, riformulate; le altre senza): "
             "hit@1 e hit@5 = la sezione giusta è la prima / tra le prime 5; MRR = media di 1/posizione.", "",
             "| Embedder | Bonus parole | hit@1 | hit@5 | MRR | Miglior punteggio (con risposta) | Miglior punteggio (senza) |",
             "|---|---|---|---|---|---|---|"]
    lines += [f"| `{r.embedder}` | {'sì' if r.bonus else 'no'} | {_percent(r.hit_at_1)} | {_percent(r.hit_at_5)} | {r.mrr:.2f} | "
              f"{r.best_score_answerable:.2f} | {'—' if r.best_score_unanswerable is None else f'{r.best_score_unanswerable:.2f}'} |"
              for r in results]
    for result in results:
        if result.misses:
            lines += ["", f"## Non trovate · `{result.embedder}`, bonus {'sì' if result.bonus else 'no'}", ""]
            lines += [f"- {question}" for question in result.misses]
    return "\n".join(lines) + "\n"
