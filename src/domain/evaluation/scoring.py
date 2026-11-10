"""How an evaluation judges its results, without LLM (deterministic, free).

**WIP**: a proposal is right when it has the expected kind, the same activity
(``activity_title``, case-insensitive) and the same item (``item``) or a
similar text: at least ``SIMILAR`` of the expected words, compared by their
first ``STEM`` letters (so «nota» meets «note»). Each expected proposal
matches at most one proposal.

**RAG**: the rank of the right section among the results, hit@k and MRR."""
import re
import unicodedata

from models.domain.wip import ProposalKind, WipProposal

SIMILAR = 0.5
STEM = 5
_WORD = re.compile(r"[a-z0-9]+")
_COMMON = frozenset("il lo la i gli le un uno una di del della dei delle a al alla da in nel nella con su per tra fra e ed o che non".split())


def stems(text: str) -> set[str]:
    plain = "".join(char for char in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(char))
    return {word[:STEM] for word in _WORD.findall(plain) if len(word) >= 3 and word not in _COMMON}


def similar(expected: str, actual: str) -> bool:
    """At least ``SIMILAR`` of the expected words (by stem) are in ``actual``."""
    wanted = stems(expected)
    return not wanted or len(wanted & stems(actual)) / len(wanted) >= SIMILAR


def matches(expected: dict, proposal: WipProposal) -> bool:
    """One expected proposal of the data set against one the model made."""
    if proposal.kind != ProposalKind(expected["kind"]):
        return False
    if proposal.kind == ProposalKind.NEW_ACTIVITY:
        return similar(expected.get("title", ""), proposal.title)
    if proposal.activity_title.casefold() != str(expected.get("activity_title", "")).casefold():
        return False
    if proposal.kind == ProposalKind.ADD_ITEM:
        return similar(expected.get("text", ""), proposal.text)
    return proposal.item == expected.get("item")


def compare(expected: list[dict], proposals: list[WipProposal]) -> tuple[int, list[dict], list[WipProposal]]:
    """How many are right, the expected ones missing, the proposals not expected."""
    left = list(proposals)
    missing = []
    for item in expected:
        found = next((proposal for proposal in left if matches(item, proposal)), None)
        if found is None:
            missing.append(item)
        else:
            left.remove(found)
    return len(expected) - len(missing), missing, left


def describe_expected(item: dict) -> str:
    target = item.get("title") or item.get("text") or f"voce {item.get('item')}"
    where = f" in «{item['activity_title']}»" if item.get("activity_title") else ""
    return f"{item['kind']}: {target}{where}"


def describe(proposal: WipProposal) -> str:
    target = proposal.title or proposal.text or f"voce {proposal.item}"
    where = f" in «{proposal.activity_title}»" if proposal.activity_title else ""
    return f"{proposal.kind.value}: {target}{where}"


def rank(results: list[tuple[str, str]], path: str, section: str) -> int | None:
    """1-based position of (path, section) in the results; None when missing."""
    return next((position for position, hit in enumerate(results, 1) if hit == (path, section)), None)


def retrieval(ranks: list[int | None]) -> tuple[float, float, float]:
    """hit@1, hit@5 and MRR of these ranks (0 for no questions)."""
    if not ranks:
        return 0.0, 0.0, 0.0
    count = len(ranks)
    return (round(sum(r == 1 for r in ranks) / count, 3), round(sum(r is not None and r <= 5 for r in ranks) / count, 3),
            round(sum(1 / r for r in ranks if r) / count, 3))
