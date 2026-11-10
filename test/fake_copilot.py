"""A fake GitHub Copilot CLI for the tests: answers ``copilot -p`` like the
real one (JSONL with ``assistant.message`` and ``result``), remembers the turns
of each ``--session-id`` (in ``$FAKE_COPILOT_STATE``) and records the
arguments it got. What it does depends on the task: the session's first
prompt and, as the real one would read it, the ``task.md`` of the
``mbare-pilot/<task>`` folder that prompt names (relative to the working
directory):

- default: plan turns answer with a question; the execution writes ``copilot.txt``;
- ``COMMIT``: the execution also commits (a broken rule, for the HEAD check);
- ``SLEEP``: the execution sleeps (for cancellation and timeouts);
- ``FAIL``: the execution fails (exit code 1, message on stderr);
- ``VIAMCP`` (with ``--additional-mcp-config``): it uses the app's MCP server as
  the real one would. Plan turns read the task (``read_task``) and quote its
  objective; the execution asks the user (``ask_user``, with ``ASK`` too),
  writes the answer in ``copilot.txt`` and calls ``finish``.

In plan mode it never writes in the working directory, as the real CLI. With
``--usage-output-file`` it writes the session's cumulative usage like the real
one: each turn adds 1 premium request, 0.1 AI credits, 1000 input and 10 output
tokens (a turn killed while sleeping writes nothing)."""
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
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
    task = _task(turns[0]["prompt"])

    usage_file = args[args.index("--usage-output-file") + 1] if "--usage-output-file" in args else None
    model = args[args.index("--model") + 1] if "--model" in args else "fake-default"
    mcp = _mcp_config(args) if "VIAMCP" in task else None
    if mode == "plan" and mcp:
        task_data = _call(mcp, "read_task", {})
        _answer(f"Ho letto via MCP: {task_data['objective']} ({len(_call(mcp, 'list_references', {}))} riferimenti)", len(turns))
        _usage(usage_file, len(turns), model)
        return 0
    if mode == "plan":
        _answer(f"Domanda {len(turns)}: confermi? (turni in questa sessione: {len(turns)})", len(turns))
        _usage(usage_file, len(turns), model)
        return 0
    if "FAIL" in task:
        print("errore simulato", file=sys.stderr)
        _answer("Non ce l'ho fatta.", len(turns), exit_code=1)
        _usage(usage_file, len(turns), model)
        return 1
    if "SLEEP" in task:
        time.sleep(60)
    if mcp:
        name = _call(mcp, "ask_user", {"question": "Che nome uso?"}) if "ASK" in task else "nessuna domanda"
        Path("copilot.txt").write_text(f"scritto da Copilot via MCP: {name}\n", encoding="utf-8")
        _call(mcp, "finish", {"summary": f"Creato copilot.txt ({name})."})
        _answer("Fatto via MCP.", len(turns))
        _usage(usage_file, len(turns), model)
        return 0
    Path("copilot.txt").write_text("scritto da Copilot\n", encoding="utf-8")
    if "COMMIT" in task:
        subprocess.run(["git", "add", "copilot.txt"], check=True, capture_output=True)
        subprocess.run(["git", "-c", "user.name=Copilot", "-c", "user.email=c@example.com", "commit", "-qm", "copilot"],
                       check=True, capture_output=True)
    _answer("Ho creato copilot.txt. Criteri soddisfatti.", len(turns))
    _usage(usage_file, len(turns), model)
    return 0


def _mcp_config(args: list[str]) -> dict | None:
    """The app's MCP server from ``--additional-mcp-config @file``, as the real CLI reads it."""
    if "--additional-mcp-config" not in args:
        return None
    value = args[args.index("--additional-mcp-config") + 1]
    config = json.loads(Path(value[1:]).read_text(encoding="utf-8") if value.startswith("@") else value)
    return config["mcpServers"]["mbare-pilot"]


def _call(server: dict, tool: str, arguments: dict):
    """One MCP tool call (JSON-RPC over HTTP); the structured result, or the text."""
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": arguments}}).encode()
    headers = {**server["headers"], "Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    with urllib.request.urlopen(urllib.request.Request(server["url"], data=body, headers=headers), timeout=60) as response:
        result = json.loads(response.read())["result"]
    if result.get("isError"):
        raise SystemExit(f"MCP {tool}: {result['content'][0]['text']}")
    structured = result.get("structuredContent")
    if structured is None:  # an unstructured answer: its text (JSON when it is data)
        text = result["content"][0]["text"] if result.get("content") else ""
        try:
            return json.loads(text)
        except ValueError:
            return text
    return structured.get("result", structured) if isinstance(structured, dict) and set(structured) == {"result"} else structured


def _task(first_prompt: str) -> str:
    """The first prompt plus the task file it points to, when there is one."""
    match = re.search(r"mbare-pilot/[\w.-]+", first_prompt)
    task_file = Path(match.group(0)) / "task.md" if match else None
    return first_prompt + ("\n" + task_file.read_text(encoding="utf-8") if task_file and task_file.is_file() else "")


def _answer(text: str, premium_requests: int, exit_code: int = 0) -> None:
    print(json.dumps({"type": "assistant.message_delta", "data": {"deltaContent": text[:5]}}))
    print(json.dumps({"type": "assistant.message", "data": {"content": ""}}))  # a tool request without text
    print(json.dumps({"type": "assistant.message", "data": {"content": text}}))
    print(json.dumps({"type": "result", "exitCode": exit_code, "usage": {"premiumRequests": premium_requests}}))
    sys.stdout.flush()


def _usage(path: str | None, turns: int, model: str) -> None:
    """The session's totals after ``turns`` turns, in the real CLI's format."""
    if path is None:
        return
    usage = {"inputTokens": 1000 * turns, "outputTokens": 10 * turns, "cacheReadTokens": 500 * turns,
             "cacheWriteTokens": 100 * turns, "reasoningTokens": 5 * turns}
    Path(path).write_text(json.dumps({
        "totalPremiumRequestCost": turns, "totalNanoAiu": 100_000_000 * turns, "totalApiDurationMs": 50 * turns,
        "modelMetrics": {model: {"requests": {"count": turns, "cost": turns}, "usage": usage}},
        "currentModel": model,
    }), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
