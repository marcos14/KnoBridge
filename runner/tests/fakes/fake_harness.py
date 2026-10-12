"""Fake ``claude`` and ``codex`` CLIs (docs/specs/harness.md, "Executáveis falsos").

They emit the JSONL of the real CLIs for the scenario in FAKE_HARNESS_SCENARIO, record the
arguments, the prompt read from stdin and the schema in FAKE_HARNESS_ARGV_FILE (one JSON line per
call) and read the success output from FAKE_HARNESS_OUTPUT (default: a minimal valid output).
Never call a model or the network. Output is ASCII-only JSON, so the console code page of the
child does not matter.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import cast

SCENARIOS = (
    "success",
    "success_stdout_only",
    "no_json_then_rescue",
    "no_json",
    "no_json_no_session",
    "invalid_json",
    "auth",
    "quota",
    "hang",
    "unsafe_tool",
    "budget",
    "crash",
)
CLAUDE_SESSION = "fake-session-1"
CODEX_THREAD = "fake-thread-1"
HANG_SECONDS = 3600

SOURCE = {"arquivo": "src/rules.py", "linha_inicial": 1, "linha_final": 2, "simbolo": None}
DEFAULT_OUTPUT: dict[str, object] = {
    "schema_version": 1,
    "objetivo": "Calcula uma regra sintetica.",
    "regras": [
        {
            "titulo": "Regra sintetica",
            "enunciado": "O valor precisa ser positivo.",
            "quando": "Ao salvar.",
            "mensagem": None,
            "resolucao": "Informar um valor positivo.",
            "parametros": [],
            "classificacao": "observado",
            "relevancia": "media",
            "fontes": [SOURCE],
        }
    ],
    "mensagens": [],
    "fluxo_principal": [{"ordem": 1, "passo": "Salvar o valor.", "fontes": [SOURCE]}],
    "faq": [],
    "duvidas": [],
}
INVALID_OUTPUT = {"schema_version": 2, "objetivo": "fora do schema"}


def emit(event: object) -> None:
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()


def hang(spawn_child: bool) -> None:
    """Never finish; optionally with a grandchild that also holds stdout (tree kill check)."""
    if spawn_child:
        subprocess.Popen(
            [sys.executable, "-c", f"import time; time.sleep({HANG_SECONDS})"],
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
    time.sleep(HANG_SECONDS)


def success_output() -> object:
    path = os.environ.get("FAKE_HARNESS_OUTPUT")
    if path:
        return cast(object, json.loads(Path(path).read_text(encoding="utf-8")))
    return DEFAULT_OUTPUT


def record(executor: str, argv: list[str], prompt: str, schema: str | None) -> None:
    path = os.environ.get("FAKE_HARNESS_ARGV_FILE")
    if not path:
        return
    leaked = sorted(k for k in os.environ if k.startswith(("KNOBRIDGE_", "CLAUDECODE")))
    call = {
        "executor": executor,
        "argv": argv,
        "stdin": prompt,
        "schema": schema,
        "cwd": str(Path.cwd()),
        "leaked_env": leaked,
    }
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(call) + "\n")


def value_after(argv: list[str], flag: str) -> str | None:
    return argv[argv.index(flag) + 1] if flag in argv else None


def claude_result(scenario: str, resume: bool) -> dict[str, object] | None:
    usage = {
        "input_tokens": 10,
        "cache_creation_input_tokens": 20,
        "cache_read_input_tokens": 30,
        "output_tokens": 40,
    }
    base: dict[str, object] = {"type": "result", "total_cost_usd": 0.02, "num_turns": 3}
    good = {**base, "subtype": "success", "is_error": False, "usage": usage}
    if scenario == "success" or (scenario == "no_json_then_rescue" and resume):
        return {**good, "structured_output": success_output()}
    if scenario == "no_json_then_rescue":
        return {**base, "subtype": "error_max_structured_output_retries", "is_error": True}
    if scenario in ("no_json", "no_json_no_session"):
        return good
    if scenario == "invalid_json":
        return {**good, "structured_output": INVALID_OUTPUT}
    if scenario == "auth":
        error = {"subtype": "success", "is_error": True, "result": "Not logged in"}
        return {**base, **error, "errors": ["Please run /login"]}
    if scenario == "quota":
        text = "You've hit your session limit - resets 9:20pm (America/Sao_Paulo)"
        return {**base, "subtype": "success", "is_error": True, "result": text}
    if scenario == "budget":
        return {"type": "result", "subtype": "error_max_budget_usd", "is_error": True}
    return None


def run_claude(argv: list[str], scenario: str) -> int:
    resume = "--resume" in argv
    session = {} if scenario == "no_json_no_session" else {"session_id": CLAUDE_SESSION}
    sys.stdout.write("fake claude banner (not JSON)\n[]\n")
    emit({"type": "system", "subtype": "init", "model": "fake-claude", **session})
    emit({"type": "rate_limit_event", "rate_limit_info": {"status": "allowed"}})
    emit({"type": "assistant", "message": {"content": "plain text"}})
    read = {"type": "tool_use", "name": "Read", "input": {"file_path": "src/rules.py"}}
    emit({"type": "assistant", "message": {"content": ["x", {"type": "text"}, read]}})
    if scenario == "hang":
        hang(spawn_child=True)
    if scenario == "unsafe_tool":
        emit({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Edit"}]}})
        hang(spawn_child=False)
    if scenario == "crash":
        sys.stderr.write("fake claude crashed\n")
        return 3
    result = claude_result(scenario, resume)
    if result is not None:
        emit({**result, **session})
    return 1 if scenario in ("auth", "quota", "budget") else 0


def codex_message(scenario: str, resume: bool) -> str:
    if scenario.startswith("success") or (scenario == "no_json_then_rescue" and resume):
        return json.dumps(success_output())
    if scenario == "invalid_json":
        return json.dumps(INVALID_OUTPUT)
    return "Terminei a leitura."


def run_codex(argv: list[str], scenario: str) -> int:
    resume = argv[:2] == ["exec", "resume"]
    last_message = value_after(argv, "--output-last-message")
    emit({"type": "thread.started", "thread_id": CODEX_THREAD})
    emit({"type": "turn.started"})
    command = {"type": "command_execution", "command": "rg -n regra", "status": "completed"}
    emit({"type": "item.started", "item": {**command, "status": "in_progress"}})
    emit({"type": "item.completed", "item": {"type": "reasoning", "text": "lendo"}})
    emit({"type": "item.completed", "item": command})
    if scenario == "hang":
        hang(spawn_child=True)
    if scenario == "unsafe_tool":
        emit({"type": "item.started", "item": {"type": "file_change", "changes": []}})
        hang(spawn_child=False)
    failures = {
        "auth": "unexpected status 401 Unauthorized: please run codex login",
        "quota": "You've hit your usage limit. Try again at 9:20 PM.",
        "crash": "stream disconnected before completion",
    }
    if scenario in failures:
        emit({"type": "error", "message": failures[scenario]})
        emit({"type": "turn.failed", "error": {"message": failures[scenario]}})
        return 1
    text = codex_message(scenario, resume)
    emit({"type": "item.completed", "item": {"type": "agent_message", "text": text}})
    if last_message and scenario != "success_stdout_only":
        Path(last_message).write_text(text, encoding="utf-8")
    usage = {"input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 20}
    emit({"type": "turn.completed", "usage": usage})
    return 0


def main(executor: str, argv: list[str]) -> int:
    scenario = os.environ.get("FAKE_HARNESS_SCENARIO", "success")
    if scenario not in SCENARIOS:
        sys.stderr.write(f"unknown FAKE_HARNESS_SCENARIO {scenario!r}\n")
        return 2
    # Bytes + explicit UTF-8: the child's console code page must not change the prompt.
    prompt = sys.stdin.buffer.read().decode("utf-8")
    if executor == "claude_code":
        record(executor, argv, prompt, value_after(argv, "--json-schema"))
        return run_claude(argv, scenario)
    schema_file = value_after(argv, "--output-schema")
    schema = Path(schema_file).read_text(encoding="utf-8") if schema_file else None
    record(executor, argv, prompt, schema)
    return run_codex(argv, scenario)
