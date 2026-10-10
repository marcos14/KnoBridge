"""Validate the YAML frontmatter of the plans in docs/planos/ (see docs/planos/AGENTS.md).

Usage: ``python check_plans.py [DIR]``. DIR defaults to ``docs/planos`` in the repository.
Prints one ``file: message`` line per problem. Exit code 0 when every plan is valid, 1 when
any problem is found, 2 on bad input.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path
from typing import cast

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PLANS_DIR = REPO_ROOT / "docs" / "planos"

PLAN_FILE_RE = re.compile(r"^(?P<id>\d{4})-(?P<slug>.+)\.md$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DELIMITER = "---"

REQUIRED_FIELDS = (
    "id",
    "titulo",
    "slug",
    "solicitado_por",
    "criado_em",
    "atualizado_em",
    "status",
    "aprovado_em",
    "aprovado_por",
    "concluido_em",
    "branch",
    "fases",
    "decisoes",
    "pendencias_usuario",
)
PHASE_FIELDS = ("id", "titulo", "status")
SUBPHASE_FIELDS = ("id", "titulo", "status", "agente", "iniciada_em", "concluida_em", "commit")
PLAN_DATE_FIELDS = ("criado_em", "atualizado_em", "aprovado_em", "concluido_em")
SUBPHASE_DATE_FIELDS = ("iniciada_em", "concluida_em")

PLAN_STATUSES = frozenset(
    {
        "rascunho",
        "aguardando_aprovacao",
        "aprovado",
        "em_execucao",
        "bloqueado",
        "concluido",
        "cancelado",
    }
)
APPROVED_STATUSES = frozenset({"aprovado", "em_execucao", "concluido"})
STEP_STATUSES = frozenset({"pendente", "em_execucao", "concluida", "bloqueada", "cancelada"})
FINISHED_STEP_STATUSES = frozenset({"concluida", "cancelada"})
PENDING_STATUSES = frozenset({"aberta", "respondida"})
DECIDED_BY = frozenset({"agente", "usuario"})


class PlanLoader(yaml.SafeLoader):
    """SafeLoader that keeps numbers and dates as strings.

    YAML 1.1 reads ``0010`` as the octal int 8 and ``2026-10-10`` as a ``date``; plan ids, commit
    hashes and dates must be compared as written, so those implicit resolvers are dropped.
    """


_DROPPED_TAGS = frozenset(
    {"tag:yaml.org,2002:int", "tag:yaml.org,2002:float", "tag:yaml.org,2002:timestamp"}
)
PlanLoader.yaml_implicit_resolvers = {
    first: [(tag, regexp) for tag, regexp in resolvers if tag not in _DROPPED_TAGS]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def as_mapping(value: object) -> dict[str, object] | None:
    return cast("dict[str, object]", value) if isinstance(value, dict) else None


def as_list(value: object) -> list[object] | None:
    return cast("list[object]", value) if isinstance(value, list) else None


def extract_frontmatter(text: str) -> str | None:
    """Return the text between the opening and closing ``---`` lines, or None."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != DELIMITER:
        return None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == DELIMITER:
            return "\n".join(lines[1:index])
    return None


def check_date(value: object, where: str) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str) and DATE_RE.match(value):
        try:
            date.fromisoformat(value)
        except ValueError:
            pass
        else:
            return []
    return [f"{where} must be null or a date AAAA-MM-DD, got {value!r}"]


def check_fields(data: dict[str, object], fields: tuple[str, ...], where: str) -> list[str]:
    return [f"{where} is missing field '{field}'" for field in fields if field not in data]


def check_subphase(raw: object, where: str) -> tuple[list[str], object]:
    """Validate one subphase; return its errors and its status."""
    subphase = as_mapping(raw)
    if subphase is None:
        return [f"{where} must be a mapping"], None
    errors = check_fields(subphase, SUBPHASE_FIELDS, where)
    status = subphase.get("status")
    if "status" in subphase and status not in STEP_STATUSES:
        errors.append(f"{where} has invalid status {status!r}")
    for field in SUBPHASE_DATE_FIELDS:
        errors += check_date(subphase.get(field), f"{where}.{field}")
    return errors, status


def check_phases(raw: object) -> tuple[list[str], list[object]]:
    """Validate 'fases'; return errors and the status of every subphase."""
    phases = as_list(raw)
    if phases is None:
        return ["'fases' must be a list"], []
    errors: list[str] = []
    statuses: list[object] = []
    for index, raw_phase in enumerate(phases):
        phase = as_mapping(raw_phase)
        where = f"fases[{index}]"
        if phase is None:
            errors.append(f"{where} must be a mapping")
            continue
        errors += check_fields(phase, PHASE_FIELDS, where)
        if "status" in phase and phase["status"] not in STEP_STATUSES:
            errors.append(f"{where} has invalid status {phase['status']!r}")
        subphases = as_list(phase.get("subfases"))
        if subphases is None:
            errors.append(f"{where}.subfases must be a list")
            continue
        for sub_index, raw_subphase in enumerate(subphases):
            sub_errors, status = check_subphase(raw_subphase, f"{where}.subfases[{sub_index}]")
            errors += sub_errors
            statuses.append(status)
    return errors, statuses


def check_items(raw: object, name: str, field: str, allowed: frozenset[str]) -> list[str]:
    """Validate a list of mappings whose FIELD must be one of ALLOWED."""
    items = as_list(raw)
    if items is None:
        return [f"'{name}' must be a list"]
    errors: list[str] = []
    for index, raw_item in enumerate(items):
        item = as_mapping(raw_item)
        where = f"{name}[{index}]"
        if item is None:
            errors.append(f"{where} must be a mapping")
        elif item.get(field) not in allowed:
            errors.append(
                f"{where}.{field} must be one of {sorted(allowed)}, got {item.get(field)!r}"
            )
    return errors


def check_identity(data: dict[str, object], file_name: str) -> list[str]:
    match = PLAN_FILE_RE.match(file_name)
    if match is None:
        return [f"file name must look like NNNN-slug.md, got {file_name!r}"]
    errors: list[str] = []
    if "id" in data and data["id"] != match["id"]:
        errors.append(f"id {data['id']!r} does not match file name number {match['id']!r}")
    if "slug" in data and data["slug"] != match["slug"]:
        errors.append(f"slug {data['slug']!r} does not match file name slug {match['slug']!r}")
    return errors


def check_status_rules(data: dict[str, object], subphase_statuses: list[object]) -> list[str]:
    status = data.get("status")
    if status not in PLAN_STATUSES:
        return [f"invalid plan status {status!r}"]
    errors: list[str] = []
    if status in APPROVED_STATUSES:
        errors += [
            f"status {status!r} requires '{field}' to be filled"
            for field in ("aprovado_em", "aprovado_por")
            if data.get(field) is None
        ]
    if status == "concluido":
        if data.get("concluido_em") is None:
            errors.append("status 'concluido' requires 'concluido_em' to be filled")
        if any(sub not in FINISHED_STEP_STATUSES for sub in subphase_statuses):
            errors.append("status 'concluido' requires every subphase 'concluida' or 'cancelada'")
    return errors


def validate_plan(text: str, file_name: str) -> list[str]:
    """Return every problem found in one plan file (empty when valid)."""
    frontmatter = extract_frontmatter(text)
    if frontmatter is None:
        return ["missing frontmatter delimited by '---' lines"]
    try:
        loaded: object = yaml.load(frontmatter, Loader=PlanLoader)  # noqa: S506 - safe loader subclass
    except yaml.YAMLError as exc:
        return [f"invalid YAML: {' '.join(str(exc).split())}"]
    data = as_mapping(loaded)
    if data is None:
        return ["frontmatter must be a YAML mapping"]

    errors = check_fields(data, REQUIRED_FIELDS, "plan")
    errors += check_identity(data, file_name)
    phase_errors, subphase_statuses = check_phases(data.get("fases"))
    errors += phase_errors
    errors += check_status_rules(data, subphase_statuses)
    for field in PLAN_DATE_FIELDS:
        errors += check_date(data.get(field), field)
    errors += check_items(data.get("decisoes"), "decisoes", "por", DECIDED_BY)
    errors += check_items(
        data.get("pendencias_usuario"), "pendencias_usuario", "status", PENDING_STATUSES
    )
    return errors


def plan_files(directory: Path) -> list[Path]:
    return sorted(path for path in directory.glob("*.md") if re.match(r"^\d{4}-", path.name))


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the frontmatter of plan files.")
    parser.add_argument(
        "directory",
        nargs="?",
        type=Path,
        default=DEFAULT_PLANS_DIR,
        help="folder with NNNN-slug.md plans (default: docs/planos)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    directory: Path = args.directory
    if not directory.is_dir():
        print(f"error: {directory} is not a directory", file=sys.stderr)
        return 2
    files = plan_files(directory)
    problems = [
        f"{path.as_posix()}: {message}"
        for path in files
        for message in validate_plan(path.read_text(encoding="utf-8"), path.name)
    ]
    for problem in problems:
        print(problem)
    if problems:
        return 1
    print(f"OK: {len(files)} plan(s) valid.")
    return 0


if __name__ == "__main__":  # pragma: no cover - entry point; main() is tested directly
    sys.exit(main())
