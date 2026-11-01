"""coverage_new_code function: the JaCoCo coverage of the code not pushed yet
(the lines of ``src/main/java`` that the commits no remote branch has add),
compared with a threshold, as plain text (no LLM).

JaCoCo comes from the parent POM: first the alignment to the parent, as
``maven_parent_alignment`` does (same parameters, parent recognised when
empty). A repository not on the parent's version, or whose alignment cannot
be confirmed, is skipped and ``mvn`` never runs there. Elsewhere ``mvn
jacoco:report`` turns the ``jacoco.exec`` the tests left into the XML when
it is missing or older (the tests are not run).

At the top the summary — it contains «sotto soglia» only when a repository
is under the threshold, for a condition that writes a note only then — then
the repositories by outcome. A project without any ``pom.xml`` gets the one
line ``NO_POM``; one with nothing to push and nothing skipped ``NOTHING_TO_PUSH``."""
from collections.abc import Callable

from pydantic import BaseModel, Field

from function.context import FunctionContext
from function.spec import FunctionResult, FunctionSpec
from models.domain.maven import CoverageCheck, CoverageStatus, NewCodeCoverage

ALL = "*"
NO_POM = "Coverage: nessun pom.xml nei repository del progetto."
NOTHING_TO_PUSH = "Coverage: nessun commit da pushare."
BELOW_MARK = "sotto soglia"


class Params(BaseModel):
    repository: str = Field("", description="Cartella del repository nel progetto. Vuoto = usa l'input dello step; * = tutti i repository del progetto.")
    threshold: int = Field(80, ge=1, le=100, description="Soglia di coverage delle righe nuove, in percentuale (1-100).")
    parent_artifact_id: str = Field(
        "", description="artifactId del POM parent (JaCoCo viene da lì): si lancia mvn solo nei repository allineati. Vuoto = riconosciuto.",
    )
    property: str = Field(
        "", description="Proprietà dei microservizi con la versione delle librerie: un nome o un modello con * (es. *.libraries.version). "
                        "Vuoto = solo le librerie (i microservizi vengono saltati).",
    )


class Result(FunctionResult):
    coverage: NewCodeCoverage


def run(context: FunctionContext, step_input: str, params: Params) -> Result:
    repository = params.repository.strip() or step_input.strip()
    coverage = context.maven.new_code_coverage(
        context.project_name, None if repository == ALL else repository, params.threshold, params.parent_artifact_id, params.property,
    )
    return Result(text=_text(coverage, None if repository == ALL else repository), coverage=coverage)


def _text(coverage: NewCodeCoverage, repository: str | None) -> str:
    if not coverage.any_pom:
        return NO_POM if repository is None else f"Coverage: {repository or 'progetto'} non ha un pom.xml."
    group = {status: [check for check in coverage.checks if check.status is status] for status in CoverageStatus}
    if len(group[CoverageStatus.NOTHING_TO_PUSH]) == len(coverage.checks):
        return NOTHING_TO_PUSH
    below, above = group[CoverageStatus.BELOW], group[CoverageStatus.ABOVE]
    threshold = f"{coverage.threshold}%"
    if below:
        header = f"Coverage nuovo codice: {len(below)} repository {BELOW_MARK} ({threshold})."
    elif above:
        header = f"Coverage nuovo codice: tutti sopra soglia ({threshold})."
    else:
        header = f"Coverage nuovo codice (soglia {threshold}): niente di misurato."
    parent = f" {coverage.parent_artifact_id} {coverage.reference_version}".rstrip() if coverage.parent_artifact_id else ""
    sections = [header]
    sections += _section("Sotto soglia", below, _measured)
    sections += _section("Sopra soglia", above, _measured)
    sections += _section("Senza report", group[CoverageStatus.NO_REPORT], _reason)
    sections += _section(f"Saltati: non allineati al parent{parent} (mvn non lanciato)", group[CoverageStatus.NOT_ALIGNED], _reason)
    sections += _section("Saltati: allineamento al parent non verificabile (mvn non lanciato)", group[CoverageStatus.NOT_VERIFIABLE], _reason)
    sections += _section("Non letti", group[CoverageStatus.UNREADABLE], _reason)
    others = [f"{_name(check)} ({check.reason})" for check in group[CoverageStatus.NOTHING_TO_MEASURE]]
    others += [f"{_name(check)} (niente da pushare)" for check in group[CoverageStatus.NOTHING_TO_PUSH]]
    others += [f"{name or 'progetto'} (senza pom.xml)" for name in coverage.without_pom]
    if others:
        sections.append("Altri: " + ", ".join(others) + ".")
    return "\n\n".join(sections)


def _section(title: str, checks: list[CoverageCheck], line: Callable[[CoverageCheck], str]) -> list[str]:
    return [title + "\n" + "\n".join(line(check) for check in checks)] if checks else []


def _measured(check: CoverageCheck) -> str:
    commits = f"{check.unpushed} commit da pushare"
    text = f"- {_name(check)}: {check.percent:.1f}% ({check.covered}/{check.total} righe nuove coperte, {commits})"
    if check.stale:
        text += "\n  ⚠ jacoco.exec precedente all'ultimo commit: rilancia i test per un dato aggiornato"
    for item in check.uncovered:
        text += f"\n  - {item.path}: righe {_ranges(item.lines)}"
    if check.not_measured:
        text += "\n  - non nel report JaCoCo: " + ", ".join(check.not_measured)
    return text


def _reason(check: CoverageCheck) -> str:
    return f"- {_name(check)}: {check.reason}"


def _name(check: CoverageCheck) -> str:
    return check.repository or "progetto"


def _ranges(lines: list[int]) -> str:
    """``[3, 4, 5, 9]`` → ``3-5, 9``."""
    parts: list[str] = []
    start = previous = lines[0]
    for line in [*lines[1:], None]:
        if line is not None and line == previous + 1:
            previous = line
            continue
        parts.append(str(start) if start == previous else f"{start}-{previous}")
        if line is not None:
            start = previous = line
    return ", ".join(parts)


COVERAGE_NEW_CODE = FunctionSpec(
    name="coverage_new_code",
    description="Coverage JaCoCo delle righe nei commit non ancora pushati, confrontata con una soglia; solo nei repository allineati "
                "al POM parent (senza LLM).",
    params=Params,
    run=run,
)
