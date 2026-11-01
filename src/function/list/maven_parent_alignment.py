"""maven_parent_alignment function: are the project's repositories on the
version of the parent POM? As plain text (no LLM), from the root ``pom.xml``
of every repository, in the working tree.

The reference is the ``version`` of the repository whose ``artifactId`` is
``parent_artifact_id``, or, when empty, of the repository the others name as
their ``<parent>`` (recognised, so one automation fits every project). A
library is checked by the version of its ``<parent>`` (when it is that
parent), a microservice by the properties matching ``property`` (a name or a
pattern with ``*``) in its ``<properties>``. First the ones to align, with
the current and the expected version, then the aligned ones; repositories
without those fields are only named. A project without any ``pom.xml`` gets
the one line ``NO_POM``, for a condition that leaves it out of a note."""
from pydantic import BaseModel, Field

from function.context import FunctionContext
from function.spec import FunctionResult, FunctionSpec
from models.domain.maven import PomAlignment, PomCheck

NO_POM = "POM: nessun pom.xml nei repository del progetto."


class Params(BaseModel):
    parent_artifact_id: str = Field(
        "", description="artifactId del POM parent: la sua version è il riferimento. Vuoto = riconosciuto (il repository che fa da <parent> agli altri).",
    )
    property: str = Field(
        "", description="Proprietà dei microservizi con la versione delle librerie: un nome o un modello con * (es. *.libraries.version). "
                        "Vuoto = solo le librerie.",
    )


class Result(FunctionResult):
    alignment: PomAlignment


def run(context: FunctionContext, step_input: str, params: Params) -> Result:
    alignment = context.maven.parent_alignment(context.project_name, params.parent_artifact_id, params.property)
    return Result(text=_text(alignment), alignment=alignment)


def _text(alignment: PomAlignment) -> str:
    if not alignment.any_pom:
        return NO_POM
    to_align = [check for check in alignment.checks if not check.aligned]
    aligned = [check for check in alignment.checks if check.aligned]
    recognised = ", riconosciuto" if alignment.detected else ""
    where = alignment.reference_repository or "progetto"
    if alignment.reference_pom and alignment.reference_pom != "pom.xml":
        where += f"/{alignment.reference_pom}"
    if not alignment.parent_artifact_id:
        header = "POM: nessun parent riconosciuto (nessun repository del progetto fa da <parent> agli altri), niente versione di riferimento."
    elif alignment.reference_repository is None:
        header = f"POM: nessun repository del progetto ha artifactId {alignment.parent_artifact_id}, niente versione di riferimento."
    elif not alignment.reference_version:
        header = f"POM: il parent {alignment.parent_artifact_id} ({where}{recognised}) non ha una version."
    else:
        summary = f"{len(to_align)} da allineare, {len(aligned)} allineati" if to_align else f"tutti allineati ({len(aligned)})"
        header = (f"POM: allineamento al parent {alignment.parent_artifact_id} {alignment.reference_version} "
                  f"({where}{recognised}): {summary}.")
    sections = [header]
    if alignment.reference_repository is None and alignment.named_parents:
        named = ", ".join(f"{artifact} ({count})" for artifact, count in alignment.named_parents.items())
        sections.append(f"Parent dichiarati dai pom.xml del progetto: {named}. Nessuno è un pom.xml dei repository del progetto "
                        "(cercato alla radice e nei moduli).")
    if to_align:
        expected = alignment.reference_version or "?"
        sections.append("Da allineare\n" + "\n".join(f"- {_label(check)}: {check.value} → {expected}" for check in to_align))
    if aligned:
        sections.append("Allineati\n" + "\n".join(f"- {_label(check)}: {check.value}" for check in aligned))
    if alignment.unreadable:
        sections.append("Non letti\n" + "\n".join(f"- {item.repository or 'progetto'}: {item.error}" for item in alignment.unreadable))
    if alignment.property_pattern and alignment.version_properties:
        shown = ", ".join(alignment.version_properties[:15]) + (" …" if len(alignment.version_properties) > 15 else "")
        sections.append(f"Nessuna proprietà corrisponde a {alignment.property_pattern}. Proprietà con «version» nei pom.xml: {shown}.")
    others = [*alignment.not_relevant, *(f"{name} (senza pom.xml)" for name in alignment.without_pom)]
    if others:
        sections.append("Senza questi campi: " + ", ".join(name or "progetto" for name in others) + ".")
    return "\n\n".join(sections)


def _label(check: PomCheck) -> str:
    unresolved = " (non risolto)" if "${" in check.value else ""
    return f"{check.repository or 'progetto'} · {check.name}{unresolved}"


MAVEN_PARENT_ALIGNMENT = FunctionSpec(
    name="maven_parent_alignment",
    description="Confronta i pom.xml dei repository del progetto con la versione del POM parent (anche riconosciuto da solo): "
                "prima quelli da allineare (senza LLM).",
    params=Params,
    run=run,
)
