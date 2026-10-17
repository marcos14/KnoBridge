"""Command line of the evaluation set: ``uv run python -m eval <run|compare|copy-corpus>``.

Exit codes: 0 finished (even with wrong answers), 1 preparation or indexing failed, 2 invalid
input. Passwords and keys come only from environment variables.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path

import httpx

from eval.client import ApiError, KnoBridgeClient
from eval.clock import Clock, SystemClock
from eval.compare import compare_reports, load_report
from eval.config import CORPUS_DIR, DEFAULT_QUESTIONS, PACKAGE_DIR, EvalConfig
from eval.corpus import copy_corpus
from eval.execute import run_evaluation
from eval.jsonx import ShapeError, get_object
from eval.questions import LEVELS, QuestionsError, load_questions
from eval.stack import SetupError

REPO_ROOT = PACKAGE_DIR.parent.parent
SCRIPTS_DIR = PACKAGE_DIR.parent
PROVIDERS = ("fake", "openai", "anthropic", "openrouter")
PASSWORD_ENV = "KNOBRIDGE_EVAL_PASSWORD"  # noqa: S105 - the variable's name, not a password
CHAT_KEY_ENV = "KNOBRIDGE_EVAL_CHAT_KEY"
EMBEDDING_KEY_ENV = "KNOBRIDGE_EVAL_EMBEDDING_KEY"
HTTP_TIMEOUT_SECONDS = 300.0
_LABEL = re.compile(r"^[a-z0-9-]{1,30}$")
_SECRET_OPTION = re.compile(r"^--[a-z-]*(key|password|senha|token|secret)", re.IGNORECASE)
_SECRET_VALUE = re.compile(r"^(sk-|kbk_|kbi_|kbr_|kbs_)")

EPILOG = f"""\
variáveis de ambiente (nunca na linha de comando):
  {PASSWORD_ENV}       senha do --email (obrigatória)
  {CHAT_KEY_ENV}       chave do provedor de chat (obrigatória fora do fake)
  {EMBEDDING_KEY_ENV}  chave do provedor de embedding, quando ele difere do de chat

exemplo com o provedor fake contra a stack de desenvolvimento:
  uv run python -m eval copy-corpus
  uv run python -m eval run --email admin@exemplo.com.br --workspace-id <uuid> \\
    --label fake --cleanup --out ../../kb-eval/fake

códigos de saída: 0 terminou (mesmo com respostas erradas), 1 falha na preparação ou na
indexação, 2 entrada inválida.
"""


class UsageError(Exception):
    """Invalid command line or environment (exit code 2)."""


def _level_pair(text: str) -> tuple[str, str]:
    level, sep, value = text.partition("=")
    if not sep or level not in LEVELS or not value:
        raise argparse.ArgumentTypeError(f"use <nível>=<valor>, com o nível em {', '.join(LEVELS)}")
    return level, value


def _model_pair(text: str) -> tuple[str, str]:
    level, model = _level_pair(text)
    if any(ch.isspace() for ch in model):
        raise argparse.ArgumentTypeError("o modelo não pode ter espaços")
    return level, model


def _steps_pair(text: str) -> tuple[str, int]:
    level, value = _level_pair(text)
    if not value.isdigit() or not 1 <= int(value) <= 6:
        raise argparse.ArgumentTypeError("max_steps vai de 1 a 6")
    return level, int(value)


def _bounded(low: float, high: float, kind: type[int] | type[float]) -> Callable[[str], float]:
    def parse(text: str) -> float:
        try:
            value = kind(text)
        except ValueError:
            raise argparse.ArgumentTypeError(f"use um número de {low:g} a {high:g}") from None
        if not low <= value <= high:
            raise argparse.ArgumentTypeError(f"use um número de {low:g} a {high:g}")
        return value

    return parse


def _label(text: str) -> str:
    if not _LABEL.match(text):
        raise argparse.ArgumentTypeError("use [a-z0-9-], até 30 caracteres")
    return text


def _workspace(text: str) -> str:
    try:
        return str(uuid.UUID(text))
    except ValueError:
        raise argparse.ArgumentTypeError("use o id (UUID) do workspace") from None


def _levels(text: str) -> tuple[str, ...]:
    levels = tuple(part.strip() for part in text.split(",") if part.strip())
    if not levels or any(level not in LEVELS for level in levels):
        raise argparse.ArgumentTypeError(f"use níveis separados por vírgula: {', '.join(LEVELS)}")
    return levels


def _add_run(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:  # pyright: ignore[reportPrivateUsage]
    run = subparsers.add_parser(
        "run",
        help="prepara o workspace, indexa o corpus, pergunta em cada nível e grava o relatório",
        description="Pelas rotas do painel, cria no workspace a credencial, a coleção, as cinco\n"
        "fontes do corpus, o produto e a chave de API eval-<rótulo>; espera a indexação;\n"
        "configura os três níveis; faz cada pergunta pela REST pública (stream: false);\n"
        "restaura os níveis, revoga a chave e grava report.json e report.md em --out.\n"
        "Antes, rode copy-corpus. O usuário precisa ser owner ou admin do workspace\n"
        "(de preferência um workspace só para a avaliação).",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    run.add_argument(
        "--base-url", default="http://localhost:8000", help="API da stack (padrão %(default)s)"
    )
    run.add_argument(
        "--email", required=True, help=f"usuário owner ou admin; a senha vem de {PASSWORD_ENV}"
    )
    run.add_argument(
        "--workspace-id", type=_workspace, required=True, help="workspace da avaliação"
    )
    run.add_argument(
        "--chat-provider",
        choices=PROVIDERS,
        default="fake",
        help="provedor dos níveis (padrão %(default)s)",
    )
    run.add_argument(
        "--embedding-provider",
        choices=PROVIDERS,
        default="fake",
        help="provedor da coleção (padrão %(default)s)",
    )
    run.add_argument(
        "--embedding-model",
        default="fake-embedding",
        help="modelo de embedding da coleção (padrão %(default)s)",
    )
    run.add_argument(
        "--model",
        type=_model_pair,
        action="append",
        default=[],
        metavar="NÍVEL=MODELO",
        help="modelo de um nível; repita para cada nível (padrão fake-chat nos três)",
    )
    run.add_argument(
        "--max-steps",
        type=_steps_pair,
        action="append",
        default=[],
        metavar="NÍVEL=N",
        help="etapas de busca de um nível, 1 a 6 (padrão: o valor atual do nível; "
        "1 em todos = linha de base sem etapas)",
    )
    run.add_argument(
        "--rerank",
        choices=("on", "off"),
        default="on",
        help="reranker do produto (padrão %(default)s)",
    )
    run.add_argument(
        "--min-similarity",
        type=_bounded(0, 1, float),
        default=None,
        help="fixa o limiar do produto (0 a 1); sem a opção, o padrão do modelo de embedding",
    )
    run.add_argument(
        "--questions",
        type=Path,
        default=DEFAULT_QUESTIONS,
        help="arquivo de perguntas (padrão eval/perguntas.json)",
    )
    run.add_argument(
        "--levels",
        type=_levels,
        default=LEVELS,
        help="só as perguntas destes níveis, separados por vírgula",
    )
    run.add_argument(
        "--repeat",
        type=_bounded(1, 5, int),
        default=1,
        help="repetições de cada pergunta, 1 a 5 (padrão %(default)s)",
    )
    run.add_argument(
        "--sources-root",
        default="/sources/eval",
        help="onde a stack vê as pastas do corpus (padrão %(default)s; veja copy-corpus)",
    )
    run.add_argument(
        "--index-timeout",
        type=_bounded(1, 86400, float),
        default=600.0,
        help="segundos de espera pela indexação (padrão 600)",
    )
    run.add_argument(
        "--label",
        type=_label,
        default="run",
        help="rótulo dos recursos (eval-<rótulo>) e do relatório (padrão %(default)s)",
    )
    run.add_argument(
        "--cleanup",
        action="store_true",
        help="exclui no fim o produto, as fontes, a coleção e as credenciais criadas",
    )
    run.add_argument(
        "--redact-answers",
        action="store_true",
        help="não grava o texto das respostas nem as uris das citações (perguntas com dados reais)",
    )
    run.add_argument(
        "--out", type=Path, required=True, help="pasta do relatório, fora do repositório"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m eval",
        description="Conjunto de avaliação sintético do KnoBridge: roda as perguntas com gabarito "
        "contra uma stack e compara execuções (docs/specs/avaliacao.md).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_run(subparsers)
    compare = subparsers.add_parser(
        "compare",
        help="compara dois report.json e grava um Markdown",
        description="Compara duas execuções do mesmo arquivo de perguntas: configuração, resumo "
        "por nível e as perguntas que mudaram de veredito.",
    )
    compare.add_argument("report_a", type=Path, help="report.json da execução A (antes)")
    compare.add_argument("report_b", type=Path, help="report.json da execução B (depois)")
    compare.add_argument("--out", type=Path, required=True, help="arquivo Markdown de saída")
    copy = subparsers.add_parser(
        "copy-corpus",
        help="copia as pastas do corpus para a pasta montada em /sources na stack",
        description="Copia manual/, interno/ e codigo/ do corpus para --to, que o compose monta "
        "em /sources (por padrão deploy/sources/eval, vista como /sources/eval).",
    )
    copy.add_argument(
        "--to",
        type=Path,
        default=REPO_ROOT / "deploy" / "sources" / "eval",
        help="pasta de destino (padrão deploy/sources/eval)",
    )
    return parser


def _refuse_secrets(argv: list[str]) -> None:
    for token in argv:
        if _SECRET_OPTION.match(token) or _SECRET_VALUE.match(token):
            raise UsageError(
                f"chaves e senhas não vão na linha de comando; use {PASSWORD_ENV}, "
                f"{CHAT_KEY_ENV} e {EMBEDDING_KEY_ENV}"
            )


def _env_keys(
    args: argparse.Namespace, env: Mapping[str, str]
) -> tuple[str, str | None, str | None]:
    password = env.get(PASSWORD_ENV)
    if not password:
        raise UsageError(f"defina {PASSWORD_ENV} com a senha de {args.email}")
    chat_key = env.get(CHAT_KEY_ENV) or None
    embedding_key = env.get(EMBEDDING_KEY_ENV) or None
    if args.chat_provider != "fake" and chat_key is None:
        raise UsageError(f"defina {CHAT_KEY_ENV} com a chave de {args.chat_provider}")
    if args.embedding_provider == "anthropic":
        raise UsageError("a Anthropic não tem embeddings; use outro --embedding-provider")
    separate = args.embedding_provider != args.chat_provider
    if separate and args.embedding_provider != "fake" and embedding_key is None:
        raise UsageError(f"defina {EMBEDDING_KEY_ENV} com a chave de {args.embedding_provider}")
    return password, chat_key, embedding_key


def _questions_label(path: Path) -> str:
    resolved = path.resolve()
    if resolved.is_relative_to(SCRIPTS_DIR):
        return resolved.relative_to(SCRIPTS_DIR).as_posix()
    return resolved.name


def _config(args: argparse.Namespace, env: Mapping[str, str], repo_root: Path) -> EvalConfig:
    out: Path = args.out.resolve()
    if out.is_relative_to(repo_root.resolve()):
        raise UsageError(
            f"{out.as_posix()} fica dentro do repositório; grave o relatório fora dele"
        )
    password, chat_key, embedding_key = _env_keys(args, env)
    questions_path: Path = args.questions
    question_set = load_questions(questions_path)
    models: dict[str, str] = dict.fromkeys(LEVELS, "fake-chat")
    models.update(args.model)
    return EvalConfig(
        base_url=args.base_url,
        email=args.email,
        password=password,
        workspace_id=args.workspace_id,
        chat_provider=args.chat_provider,
        embedding_provider=args.embedding_provider,
        chat_key=chat_key,
        embedding_key=embedding_key,
        embedding_model=args.embedding_model,
        models=models,
        max_steps=dict(args.max_steps),
        rerank=args.rerank == "on",
        min_similarity=args.min_similarity,
        questions=question_set,
        questions_file=_questions_label(questions_path),
        questions_sha256=hashlib.sha256(questions_path.read_bytes()).hexdigest(),
        levels=args.levels,
        repeat=args.repeat,
        sources_root=args.sources_root,
        index_timeout=args.index_timeout,
        label=args.label,
        cleanup=args.cleanup,
        out=out,
        redact_answers=args.redact_answers,
    )


def _run(config: EvalConfig, transport: httpx.BaseTransport | None, clock: Clock) -> int:
    with httpx.Client(
        base_url=config.base_url, transport=transport, timeout=HTTP_TIMEOUT_SECONDS
    ) as http:
        client = KnoBridgeClient(http, config.workspace_id)
        try:
            report = run_evaluation(client, config, clock, print)
        except (SetupError, ApiError, ShapeError, httpx.HTTPError) as error:
            print(f"erro: {error}")
            return 1
        except KeyboardInterrupt:
            print("interrompido; os níveis foram restaurados e a chave revogada")
            return 1
    total = get_object(get_object(report, "summary", "$"), "total", "$.summary")
    print(
        f"relatório em {config.out.as_posix()}: "
        f"{total.get('correct')} de {total.get('questions')} respostas corretas"
    )
    return 0


def main(
    argv: list[str] | None = None,
    *,
    repo_root: Path = REPO_ROOT,
    env: Mapping[str, str] | None = None,
    transport: httpx.BaseTransport | None = None,
    clock: Clock | None = None,
) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    try:
        _refuse_secrets(raw)
        try:
            args = _parser().parse_args(raw)
        except SystemExit as exc:
            return 0 if exc.code == 0 else 2
        if args.command == "compare":
            markdown = compare_reports(load_report(args.report_a), load_report(args.report_b))
            out_md: Path = args.out
            out_md.parent.mkdir(parents=True, exist_ok=True)
            out_md.write_text(markdown, encoding="utf-8")
            print(f"comparação em {out_md.as_posix()}")
            return 0
        if args.command == "copy-corpus":
            count = copy_corpus(CORPUS_DIR, args.to)
            print(f"{count} arquivos copiados para {args.to.as_posix()}")
            return 0
        config = _config(args, os.environ if env is None else env, repo_root)
    except (UsageError, QuestionsError, ShapeError) as error:
        print(f"erro: {error}")
        return 2
    return _run(config, transport, SystemClock() if clock is None else clock)
