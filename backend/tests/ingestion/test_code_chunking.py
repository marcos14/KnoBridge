from __future__ import annotations

from chunking_support import chunks, lines_of

from knobridge.ingestion.chunk_base import MAX_TOKENS
from knobridge.ingestion.code_chunking import chunk_code, supports, unfence
from knobridge.ingestion.parsing import fence_code
from knobridge.llm.embeddings import estimate_tokens


def _body(lines: int, indent: str = "  ") -> str:
    return "\n".join(f"{indent}total = total + item{i} * rate{i};" for i in range(lines))


def _ts_function(name: str, lines: int) -> str:
    body = _body(lines)
    return f"export function {name}(): number {{\n  let total = 0;\n{body}\n  return total;\n}}\n"


def test_typescript_chunks_by_function_and_class() -> None:
    source = (
        "import { Rate } from './rate';\n"
        "\n"
        f"{_ts_function('computeTotal', 60)}"
        "\n"
        "/** Applies discounts. */\n"
        "export class DiscountService extends Base {\n"
        "  private rate = 0.1;\n"
        "  apply(value: number): number {\n"
        f"{_body(60, '    ')}\n"
        "    return value;\n"
        "  }\n"
        "}\n"
        "\n"
        "export interface Invoice { id: string; total: number }\n"
        "type Id = string;\n"
        "enum Status { Open, Paid }\n"
        "const format = (value: number): string => value.toFixed(2);\n"
        "export default function () { return 1; }\n"
    )

    result = chunks("src/billing.ts", source)

    symbols = [c.meta.get("symbol") for c in result]
    assert symbols == [
        "computeTotal",
        "DiscountService",
        "Invoice, Id, Status, format, default",
    ]
    assert result[0].display.startswith("import { Rate }")
    service = result[1]
    assert service.display.startswith("/** Applies discounts. */")
    assert service.meta["node_type"] == "class"
    assert "node_type" not in result[2].meta
    assert all(c.meta["language"] == "typescript" for c in result)


def test_code_chunk_metadata_has_symbol_and_lines() -> None:
    source = (
        "// helpers\n"
        "import x from 'y';\n"
        "\n"
        f"{_ts_function('first', 80)}"
        "\n"
        f"{_ts_function('second', 80)}"
    )

    result = chunks("src/calc.ts", source)

    assert [c.meta.get("symbol") for c in result] == ["first", "second"]
    first = result[0]
    assert lines_of(first) == (1, 87)
    assert first.content.startswith("path: src/calc.ts\nsymbol: first\n\n// helpers\n")
    assert first.display == "\n".join(source.split("\n")[0:87])
    assert first.meta["node_type"] == "function"
    assert lines_of(result[1]) == (89, 172)


def test_large_class_splits_into_methods() -> None:
    methods = "\n".join(
        f"  // method {n}\n  m{n}(): number {{\n{_body(70, '    ')}\n    return 0;\n  }}"
        for n in range(3)
    )
    source = f"class Ledger {{\n  balance = 0;\n{methods}\n}}\n"

    result = chunks("src/ledger.ts", source)

    assert [c.meta.get("symbol") for c in result] == ["Ledger.m0", "Ledger.m1", "Ledger.m2"]
    assert all(c.meta["parent"] == "Ledger" for c in result)
    assert all(c.meta["node_type"] == "method" for c in result)
    assert result[0].display.startswith("  balance = 0;")
    assert result[1].display.startswith("  // method 1")


def test_huge_function_is_split_by_lines() -> None:
    source = _ts_function("giant", 400)

    result = chunks("src/giant.js", source)

    assert len(result) > 2
    assert all(c.meta["symbol"] == "giant" for c in result)
    assert all(c.meta["language"] == "javascript" for c in result)
    assert all(c.content.startswith("path: src/giant.js\nsymbol: giant\n\n") for c in result)
    assert lines_of(result[0])[0] == 1
    assert lines_of(result[-1])[1] == 404


def test_tsx_and_jsx_components() -> None:
    tsx = "export const Card = ({ title }: { title: string }) => <div>{title}</div>;\n"
    jsx = "function App() { return <main />; }\nlet a = 1, b = 2;\n"

    tsx_chunks = chunks("ui/card.tsx", tsx)
    jsx_chunks = chunks("ui/app.jsx", jsx)

    assert tsx_chunks[0].meta["symbol"] == "Card"
    assert tsx_chunks[0].meta["language"] == "tsx"
    assert jsx_chunks[0].meta["symbol"] == "App"
    assert lines_of(jsx_chunks[0]) == (1, 2)


def test_go_chunks_by_func_and_method() -> None:
    body = "\n".join(f"\ttotal += item{i} * rate{i}" for i in range(60))
    source = (
        "package billing\n"
        "\n"
        'import "fmt"\n'
        "\n"
        "// Store keeps invoices.\n"
        "type Store[T any] struct {\n\titems []T\n}\n"
        "\n"
        f"func (s *Store[T]) Total() int {{\n\ttotal := 0\n{body}\n\treturn total\n}}\n"
        "\n"
        f"func Format(v int) string {{\n\ttotal := 0\n{body}\n\treturn fmt.Sprint(v)\n}}\n"
        "\n"
        "type Reader interface {\n\tRead() int\n}\n"
        "type (\n\tA int\n\tB string\n)\n"
        "type Alias = int\n"
        "var limit = 10\n"
    )

    result = chunks("pkg/billing/store.go", source)

    symbols = [c.meta.get("symbol") for c in result]
    assert symbols == ["Store", "Store.Total", "Format", "Reader, A, B, Alias"]
    store, method, function = result[0], result[1], result[2]
    assert store.display.startswith("package billing")
    assert "// Store keeps invoices." in store.display
    assert store.meta["node_type"] == "struct"
    assert method.meta["parent"] == "Store"
    assert method.meta["node_type"] == "method"
    assert lines_of(method) == (10, 73)
    assert function.meta["node_type"] == "function"
    assert "node_type" not in result[3].meta
    assert all(c.meta["language"] == "go" for c in result)


def test_go_method_metadata() -> None:
    source = "package p\n\nfunc (r Repo) Find() {}\n\nfunc (Repo) Count() {}\n"

    result = chunks("p/repo.go", source)

    assert result[0].meta["symbol"] == "Repo.Find, Repo.Count"
    assert result[0].meta["parent"] == "Repo"
    assert result[0].meta["node_type"] == "method"


def test_go_single_type_kinds() -> None:
    struct = chunks("p/s.go", "package p\n\ntype S struct{}\n")
    iface = chunks("p/i.go", "package p\n\ntype I interface{}\n")
    named = chunks("p/n.go", "package p\n\ntype N int\n")

    assert struct[0].meta["node_type"] == "struct"
    assert iface[0].meta["node_type"] == "interface"
    assert named[0].meta["node_type"] == "type"


def test_unknown_language_falls_back_to_lines() -> None:
    source = "\n".join(f"def step_{i}():\n    return {i}\n" for i in range(150))

    result = chunks("tools/steps.py", source)

    assert len(result) > 1
    assert all("symbol" not in c.meta for c in result)
    assert all(c.meta["language"] == "python" for c in result)
    assert all(c.content.startswith("path: tools/steps.py\n\n") for c in result)
    assert lines_of(result[0])[0] == 1


def test_file_without_symbols_falls_back_to_lines() -> None:
    source = "import a from 'a';\n// note\nexport const LIMIT = 10;\nconsole.log(LIMIT);\n"

    result = chunks("src/consts.ts", source)

    assert len(result) == 1
    assert result[0].meta == {
        "path": "src/consts.ts",
        "language": "typescript",
        "start_line": 1,
        "end_line": 4,
    }


def test_detached_comment_is_not_attached() -> None:
    source = "// license\n\n// docs\nfunction f() {}\n"

    result = chunk_code(source, "a.js", "javascript")

    assert result[0].meta["symbol"] == "f"
    assert result[0].meta["start_line"] == 1


def test_export_without_declaration_and_trailing_comment() -> None:
    source = "export { a, b };\nclass K { m() {} }\n// end\n"

    result = chunk_code(source, "k.ts", "typescript")

    assert result[0].meta["symbol"] == "K"
    assert result[0].meta["end_line"] == 3


def test_large_code_without_symbol_is_split() -> None:
    table = "\n".join(f"  ['code{i:03d}', 'descrição do código {i}']," for i in range(200))
    source = f"function lookup() {{ return 1; }}\nconst TABLE = [\n{table}\n];\n"

    result = chunk_code(source, "src/table.js", "javascript")

    assert result[0].meta["symbol"] == "lookup"
    assert len(result) > 2
    assert all("symbol" not in c.meta for c in result[1:])
    assert all(c.content.startswith("path: src/table.js\n\n") for c in result[1:])


def test_chunk_code_without_language() -> None:
    result = chunk_code("x = 1\n", "Makefile", None)

    assert result[0].meta == {"path": "Makefile", "start_line": 1, "end_line": 1}
    assert not supports(None)
    assert supports("go")


def test_unfence_returns_original_code() -> None:
    code = "const a = 1;\n```\nconst b = 2;\n"

    assert unfence(fence_code(code, "typescript")) == code.rstrip("\n")
    assert unfence(fence_code("", "go")) == ""


def test_chunks_stay_within_max_tokens() -> None:
    source = "\n".join(_ts_function(f"f{i}", 30 + i * 7) for i in range(12))

    result = chunks("src/many.ts", source)

    assert all(estimate_tokens(c.display) <= MAX_TOKENS for c in result)
    assert lines_of(result[0])[0] == 1
    assert lines_of(result[-1])[1] == len(source.split("\n")) - 1
    assert [c.position for c in result] == list(range(len(result)))
