"""A fake GitHub Copilot CLI for the tests: answers ``copilot -p`` like the
real one (JSONL with ``assistant.message`` and ``result``), remembers the turns
of each ``--session-id`` (in ``$FAKE_COPILOT_STATE``) and records the
arguments it got. What it does depends on the task (the session's first prompt):

- default: plan turns answer with a question; the execution writes ``copilot.txt``;
- ``COMMIT``: the execution also commits (a broken rule, for the HEAD check);
- ``SLEEP``: the execution sleeps (for cancellation and timeouts);
- ``FAIL``: the execution fails (exit code 1, message on stderr).

In plan mode it never writes in the working directory, as the real CLI."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path


def main() -> int:
    args = sys.argv[1:]
    prompt = args[args.index("-p") + 1]
    session_id = args[args.index("--session-id") + 1]
    mode = args[args.index("--mode") + 1]
    state = Path(os.environ["FAKE_COPILOT_STATE"])
    state.mkdir(parents=True, exist_ok=True)
    session_file = state / f"{session_id}.json"
    turns = json.loads(session_file.read_text(encoding="utf-8")) if session_file.exists() else []
    turns.append({"prompt": prompt, "mode": mode, "args": args})
    session_file.write_text(json.dumps(turns), encoding="utf-8")
    task = turns[0]["prompt"]

    if mode == "plan":
        _answer(f"Domanda {len(turns)}: confermi? (turni in questa sessione: {len(turns)})", len(turns))
        return 0
    if "FAIL" in task:
        print("errore simulato", file=sys.stderr)
        _answer("Non ce l'ho fatta.", len(turns), exit_code=1)
        return 1
    if "SLEEP" in task:
        time.sleep(60)
    Path("copilot.txt").write_text("scritto da Copilot\n", encoding="utf-8")
    if "COMMIT" in task:
        subprocess.run(["git", "add", "copilot.txt"], check=True, capture_output=True)
        subprocess.run(["git", "-c", "user.name=Copilot", "-c", "user.email=c@example.com", "commit", "-qm", "copilot"],
                       check=True, capture_output=True)
    _answer("Ho creato copilot.txt. Criteri soddisfatti.", len(turns))
    return 0


def _answer(text: str, premium_requests: int, exit_code: int = 0) -> None:
    print(json.dumps({"type": "assistant.message_delta", "data": {"deltaContent": text[:5]}}))
    print(json.dumps({"type": "assistant.message", "data": {"content": ""}}))  # a tool request without text
    print(json.dumps({"type": "assistant.message", "data": {"content": text}}))
    print(json.dumps({"type": "result", "exitCode": exit_code, "usage": {"premiumRequests": premium_requests}}))
    sys.stdout.flush()


if __name__ == "__main__":
    sys.exit(main())
