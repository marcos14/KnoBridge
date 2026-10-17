"""The validated options of ``run`` (docs/specs/avaliacao.md, "Linha de comando")."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from eval.questions import QuestionSet

PACKAGE_DIR = Path(__file__).resolve().parent
CORPUS_DIR = PACKAGE_DIR / "fixtures" / "corpus"
DEFAULT_QUESTIONS = PACKAGE_DIR / "perguntas.json"
# ProviderCreate requires a key of 8 or more characters; the fake provider ignores it.
FAKE_PROVIDER_KEY = "fake-eval-key"
INDEX_POLL_SECONDS = 2.0


@dataclass(frozen=True)
class EvalConfig:
    base_url: str
    email: str
    password: str
    workspace_id: str
    chat_provider: str
    embedding_provider: str
    chat_key: str | None
    embedding_key: str | None
    embedding_model: str
    models: dict[str, str]
    max_steps: dict[str, int]
    rerank: bool
    min_similarity: float | None
    questions: QuestionSet
    questions_file: str
    questions_sha256: str
    levels: tuple[str, ...]
    repeat: int
    sources_root: str
    index_timeout: float
    label: str
    cleanup: bool
    out: Path
    redact_answers: bool
    corpus_dir: Path = CORPUS_DIR

    @property
    def prefix(self) -> str:
        return f"eval-{self.label}"
