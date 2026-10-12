"""Layer 0 regex extractions: messages, environment reads, routes and module documentation."""

from __future__ import annotations

from knobridge_runner.layer0.extract import (
    MAX_DOC_CHARS,
    MAX_ENV_READS,
    MAX_MESSAGE_CHARS,
    extract,
    module_doc,
)

SERVICE_TS = """\
export function emitir(nota: Nota) {
  if (!nota.cnpj) {
    throw new Error("Informe o CNPJ do cliente antes de emitir a nota.");
  }
  const serie = process.env.NOTAS_SERIE_PADRAO ?? "1";
  const url = import.meta.env.VITE_API_URL;
  toast(`Nota ${nota.numero} emitida`);
  alert(`Falha ao gravar a nota fiscal`);
  const key = process.env["NFE_TOKEN"];
  throw new Error("Informe o CNPJ do cliente antes de emitir a nota.");
  console.log("this line has no trigger word at all here");
  throw new Error("short");
  throw new Error("1234567890123456");
}
"""

SETTINGS_PY = """\
import os
DB = os.environ["DATABASE_URL"]
DEBUG = os.environ.get('DEBUG_MODE')
LEVEL = os.getenv("LOG_LEVEL")
raise ValueError('Usuário sem permissão para cancelar o pedido')
"""

MIXED = """\
key := os.Getenv("GO_KEY")
v, ok := os.LookupEnv("GO_OPTIONAL")
String s = System.getenv("JAVA_HOME_X");
var c = Environment.GetEnvironmentVariable("DOTNET_FLAG");
token = ENV['RUBY_TOKEN']
$x = env('LARAVEL_KEY');
lower = os.getenv("not_upper")
"""


def test_extracts_user_messages_and_env_reads() -> None:
    found = extract([("src/notas.ts", SERVICE_TS), ("app/settings.py", SETTINGS_PY)])

    assert [(item.text, item.path, item.line) for item in found.messages] == [
        ("Informe o CNPJ do cliente antes de emitir a nota.", "src/notas.ts", 3),
        ("Falha ao gravar a nota fiscal", "src/notas.ts", 8),
        ("Usuário sem permissão para cancelar o pedido", "app/settings.py", 5),
    ]
    assert [(item.text, item.line) for item in found.env_reads] == [
        ("NOTAS_SERIE_PADRAO", 5),
        ("VITE_API_URL", 6),
        ("NFE_TOKEN", 9),
        ("DATABASE_URL", 2),
        ("DEBUG_MODE", 3),
        ("LOG_LEVEL", 4),
    ]


def test_extracts_env_reads_of_other_languages() -> None:
    found = extract([("cfg.txt", MIXED)])

    assert [item.text for item in found.env_reads] == [
        "GO_KEY",
        "GO_OPTIONAL",
        "JAVA_HOME_X",
        "DOTNET_FLAG",
        "RUBY_TOKEN",
        "LARAVEL_KEY",
    ]


def test_extracts_routes_with_method_and_path() -> None:
    source = """\
app.get('/clientes', listar)
router.post("/notas", emitir)
@app.delete("/notas/{id}")
@GetMapping("/pedidos")
@PostMapping(value = "/pedidos")
@RequestMapping("/api")
http.HandleFunc("/health", h)
r.GET("/items", h)
[HttpPut("produtos/{id}")]
client.get('/not-a-route-object')
app.get("relative")
"""

    found = extract([("routes.txt", source)])

    assert [item.text for item in found.routes] == [
        "GET /clientes",
        "POST /notas",
        "DELETE /notas/{id}",
        "GET /pedidos",
        "POST /pedidos",
        "ANY /api",
        "ANY /health",
        "GET /items",
        "PUT /produtos/{id}",
    ]


def test_extractions_drop_duplicates_and_respect_limits() -> None:
    lines = "".join(f'os.getenv("VAR_{index:03}")\n' for index in range(MAX_ENV_READS + 5))
    long_message = "x " * MAX_MESSAGE_CHARS

    found = extract([("a.py", lines * 2), ("b.py", f'raise Exception("{long_message}")\n')])

    assert len(found.env_reads) == MAX_ENV_READS
    assert len(found.messages[0].text) == MAX_MESSAGE_CHARS


def test_module_doc_prefers_shallow_readme() -> None:
    files = [
        ("src/x/sub/README.md", "deep"),
        ("src/x/docs/guia.md", "guide"),
        ("src/x/AGENTS.md", "agents"),
        ("src/x/README.md", "  readme\n"),
        ("src/x/code.py", "pass"),
    ]

    doc = module_doc(files)

    assert doc is not None
    assert (doc.path, doc.text) == ("src/x/README.md", "readme")


def test_module_doc_uses_docs_folder_and_caps_size() -> None:
    doc = module_doc([("m/docs/intro.md", "a" * (MAX_DOC_CHARS + 10)), ("m/x.py", "")])

    assert doc is not None
    assert (doc.path, len(doc.text)) == ("m/docs/intro.md", MAX_DOC_CHARS)


def test_module_doc_is_none_without_candidates() -> None:
    assert module_doc([("m/x.py", ""), ("docs.md", "")]) is None
