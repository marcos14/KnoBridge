"""Module keys and module patterns (docs/specs/harness.md, "Chave do módulo" and "Sugestão de
módulos").

A module's ``paths`` are gitwildmatch patterns evaluated like a ``.gitignore``: a file belongs
to the module when the last pattern that matches it is not negated (``!``). The same rule the
runner's layer 0 uses decides, on the server, which modules a commit touched.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable, Sequence

from pathspec import GitIgnoreSpec

from knobridge.harness.models import MODULE_KEY_MAX_LENGTH

_NOT_KEY = re.compile(r"[^a-z0-9]+")
_HASH_LENGTH = 8


def module_key(path: str) -> str:
    """The stable key of a folder path (or a title): accents removed, lowercase, runs of other
    characters as one ``-``; too long or empty keys get a short hash of ``path``."""
    digest = hashlib.sha256(path.encode("utf-8")).hexdigest()[:_HASH_LENGTH]
    ascii_text = unicodedata.normalize("NFKD", path).encode("ascii", "ignore").decode("ascii")
    key = _NOT_KEY.sub("-", ascii_text.lower()).strip("-")
    if not key:
        return f"module-{digest}"
    if len(key) > MODULE_KEY_MAX_LENGTH:
        head = key[: MODULE_KEY_MAX_LENGTH - _HASH_LENGTH - 1].rstrip("-")
        return f"{head}-{digest}"
    return key


def touches(paths: Sequence[str], changed: Iterable[str]) -> bool:
    """Whether any of the ``changed`` files belongs to a module with these ``paths``."""
    spec = GitIgnoreSpec.from_lines(paths)
    return any(spec.match_file(path) for path in changed)
