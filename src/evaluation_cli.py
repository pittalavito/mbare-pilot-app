"""The evaluations from the terminal (resource/scripts/eval-wip.py, eval-rag.py):
the same as the button of the Metriche page, run now instead of in the
worker. Needs the DB (the catalog of the models and their prices) and, for
real models or embedders, their keys in .env; the API is not needed.

    python src/evaluation_cli.py wip --model openrouter/google/gemini-3.1-flash-lite-preview [--model ...]
    python src/evaluation_cli.py rag [--embedder hashing] [--embedder openrouter/openai/text-embedding-3-small]

The report (markdown and JSON) goes in <MBARE_PILOT_HOME>/evaluations/; its
markdown is printed too."""
import argparse
import sys
from collections.abc import Callable

from config import Config
from core.container import Container
from core.error import AppError
from service.evaluation_service import EvaluationService


def main(argv: list[str], service: Callable[[], EvaluationService] = lambda: Container().evaluation_service) -> int:
    parser = argparse.ArgumentParser(prog="evaluation_cli", description="Valutazioni di Elabora WIP e della ricerca nel contesto.")
    kinds = parser.add_subparsers(dest="kind", required=True)
    wip = kinds.add_parser("wip", help="Elabora WIP sul set di prova, con uno o più modelli del catalogo")
    wip.add_argument("--model", action="append", required=True, help="un modello del catalogo (ripetibile)")
    rag = kinds.add_parser("rag", help="la ricerca nel contesto sul set di prova, con uno o più embedder")
    rag.add_argument("--embedder", action="append", default=[], help="hashing o openrouter/<modello> (ripetibile; default hashing)")
    args = parser.parse_args(argv)
    evaluations = service()
    try:
        name = evaluations.run_wip(args.model)[0] if args.kind == "wip" else evaluations.run_rag(args.embedder)[0]
    except AppError as exc:
        print(f"Valutazione non riuscita: {exc}", file=sys.stderr)
        return 1
    print(evaluations.report(name))
    print(f"Report: {Config.get().evaluations_root / name}.md (e .json)")
    return 0


if __name__ == "__main__":  # pragma: no cover - the scripts' entry point
    sys.exit(main(sys.argv[1:]))
