from __future__ import annotations

import asyncio
import random

import pytest
from pydantic import TypeAdapter, ValidationError

from knobridge_runner.backoff import Backoff, monotonic, real_sleep
from knobridge_runner.formats import ModulePattern, RelativePath
from knobridge_runner.protocol import (
    RunnerClaimIn,
    RunnerHeartbeatIn,
    RunnerJobMetrics,
    RunnerJobOut,
    RunnerRepositoryInfo,
)
from knobridge_runner.protocol_result import (
    ModuleContent,
    ModuleItemIn,
    RuleContent,
    RuleItemIn,
    RunnerEvidenceIn,
    RunnerExecutorRun,
    RunnerJobResultIn,
)
from runner_support import COMMIT, job_out

PATH = TypeAdapter(RelativePath)
PATTERN = TypeAdapter(ModulePattern)


@pytest.mark.parametrize("value", ["src/a.ts", "a", "dir/sub/file.name.py"])
def test_relative_path_accepts_posix_relative(value: str) -> None:
    assert PATH.validate_python(value) == value


@pytest.mark.parametrize(
    "value",
    ["", "/abs", "a\\b", "C:/x", "a//b", "./a", "a/../b", "a/.", "a\x00b", "a/", "x" * 501],
)
def test_relative_path_rejects_unsafe_values(value: str) -> None:
    with pytest.raises(ValidationError):
        PATH.validate_python(value)


@pytest.mark.parametrize("value", ["src/billing/", "**/*.ts", "!src/legacy/**", "src/[ab]?.py"])
def test_module_pattern_accepts_gitwildmatch(value: str) -> None:
    assert PATTERN.validate_python(value) == value


@pytest.mark.parametrize("value", ["/src", "!../x", "src//a", "x" * 301, "!"])
def test_module_pattern_rejects_unsafe_values(value: str) -> None:
    with pytest.raises(ValidationError):
        PATTERN.validate_python(value)


def test_repository_info_rejects_control_characters_in_branch() -> None:
    with pytest.raises(ValidationError):
        RunnerRepositoryInfo(name="erp", head_commit=COMMIT, branch="main\n", dirty=False)


def test_heartbeat_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        RunnerHeartbeatIn.model_validate(
            {
                "runner_version": "0.1.0",
                "platform": "linux",
                "executors": [],
                "repositories": [],
                "hostname": "leak",
            }
        )


def test_claim_rejects_wait_above_limit() -> None:
    with pytest.raises(ValidationError):
        RunnerClaimIn(wait_seconds=26, executors=["codex"], repositories=["erp"])


def test_job_out_ignores_unknown_response_fields() -> None:
    job = RunnerJobOut.model_validate(job_out(new_field=True))

    assert job.module.key == "src-billing"


def evidence(start: int = 1, end: int = 3, excerpt: str | None = None) -> RunnerEvidenceIn:
    return RunnerEvidenceIn(path="src/a.ts", start_line=start, end_line=end, excerpt=excerpt)


def rule_item() -> RuleItemIn:
    return RuleItemIn(
        kind="rule",
        title="Nota exige CNPJ",
        content=RuleContent(
            enunciado="A nota exige CNPJ.",
            quando="Ao emitir.",
            mensagem=None,
            resolucao="Completar o cadastro.",
            parametros=[],
            classificacao="intencional",
            relevancia="alta",
        ),
        evidence=[evidence()],
    )


def module_item() -> ModuleItemIn:
    return ModuleItemIn(
        kind="module",
        title="src/billing",
        content=ModuleContent(
            objetivo="Emite notas.", fluxo_principal=[], mensagens=[], faq=[], duvidas=[]
        ),
        evidence=[evidence()],
    )


def result(items: list[RuleItemIn | ModuleItemIn]) -> RunnerJobResultIn:
    return RunnerJobResultIn(
        attempt=1,
        commit_sha=COMMIT,
        changed_paths=["src/a.ts"],
        executor=RunnerExecutorRun(name="codex", model="gpt-5.1"),
        metrics=RunnerJobMetrics(duration_ms=1),
        items=items,
        rejections=[],
    )


def test_result_accepts_rules_and_one_module_item() -> None:
    assert len(result([rule_item(), module_item()]).items) == 2


def test_result_rejects_two_module_items() -> None:
    with pytest.raises(ValidationError, match="1 module item"):
        result([module_item(), module_item()])


def test_result_parses_items_by_kind() -> None:
    parsed = RunnerJobResultIn.model_validate_json(result([module_item()]).model_dump_json())

    assert isinstance(parsed.items[0], ModuleItemIn)


@pytest.mark.parametrize(("start", "end"), [(5, 4), (1, 81)])
def test_evidence_rejects_bad_ranges(start: int, end: int) -> None:
    with pytest.raises(ValidationError):
        evidence(start, end)


def test_evidence_rejects_excerpt_above_8_kib() -> None:
    with pytest.raises(ValidationError, match="bytes"):
        evidence(excerpt="é" * 4097)


def test_evidence_accepts_excerpt_within_limit() -> None:
    assert evidence(excerpt="x" * 8192).excerpt is not None


def test_backoff_jitter_is_seeded_and_bounded() -> None:
    first = Backoff(rng=random.Random(7))
    second = Backoff(rng=random.Random(7))

    delays = [first.delay(n) for n in range(1, 10)]

    assert delays == [second.delay(n) for n in range(1, 10)]
    assert 0.8 <= delays[0] <= 1.2
    assert all(delay <= 60 for delay in delays)


def test_real_sleep_and_monotonic_defaults_work() -> None:
    before = monotonic()

    asyncio.run(real_sleep(0))

    assert monotonic() >= before
