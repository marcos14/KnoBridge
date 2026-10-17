# scripts/eval/

**Função**: conjunto de avaliação sintético das respostas do KnoBridge (plano 0011): o corpus de um ERP fictício (Vértice ERP), as perguntas com gabarito e o roteiro que prepara um workspace na stack pela API, indexa, pergunta nos três níveis e grava `report.json` e `report.md`. O contrato está em [docs/specs/avaliacao.md](../../docs/specs/avaliacao.md). Nada aqui é dado real (regra 9).

**Entra aqui**:
- `fixtures/corpus/`: o corpus versionado (só dados, por isso sem `AGENTS.md`, que seria indexado): `manual/` (`manual-*.md`, fonte `end_user`), `interno/` (`interno-*.md`, `support`, com o esquema do banco em blocos SQL), `codigo/` (`src/**/*.ts`, `migrations/*.sql` e `gerado/*.json` grandes e repetitivos, `product_dev`), `chamados.jsonl` (`EVAL-T-nnn`) e `cards.jsonl` (`EVAL-C-nnn`).
- `perguntas.json`: as perguntas com gabarito (`eu-`, `su-`, `pd-` + número), no formato da spec.
- `questions.py` (validação do arquivo de perguntas, erro com o caminho do campo), `matching.py` (matchers `path:`/`ticket:`/`card:` e normalização), `judge.py` (`Answer`, julgamento e `AnswerRecord`), `metrics.py` (métricas e percentil do vizinho mais próximo).
- `client.py` (rotas do painel com sessão e CSRF; REST pública com a chave), `stack.py` (preparação e encerramento), `execute.py` (o `run`), `report.py` e `mdfmt.py` (relatório), `compare.py` (o `compare`), `corpus.py` (o `copy-corpus`), `config.py`, `clock.py`, `jsonx.py` (acesso tipado ao JSON) e `cli.py` (`main(argv, *, repo_root, env, transport, clock)`).

**Não entra aqui**: perguntas ou corpus com dados reais (ficam fora do repositório e entram por `--questions`), relatórios gerados (sempre fora do repositório; o `run` recusa `--out` dentro dele), código do produto.

**Convenções locais**:
- Só a API pública e as rotas do painel; nunca o banco. Nenhum teste chama a stack, um LLM ou embeddings: os testes usam `httpx.MockTransport` (`tests/eval_fake_api.py`) e um relógio falso.
- Senhas e chaves só por variável de ambiente (`KNOBRIDGE_EVAL_PASSWORD`, `KNOBRIDGE_EVAL_CHAT_KEY`, `KNOBRIDGE_EVAL_EMBEDDING_KEY`); a CLI recusa opção ou valor com cara de segredo, e nada disso vai para o relatório ou o stdout.
- Nomes de arquivo únicos no corpus, com o prefixo da pasta, para o gabarito achar a fonte pela citação. Mudou o corpus ou as perguntas: o teste `repo` confere matchers, níveis e o formato dos JSONL; valide também os JSONL contra os modelos do backend (`TicketIn`, `CardIn`).
- Mudou o formato do relatório: regenere `tests/fixtures/eval/` (`report.json`, `report.md`, `compare.md`) e revise o diff.

**Como testar** (de `scripts/`): `uv run pytest tests/test_eval_*.py` (o gate de 95% vale para o projeto inteiro: `uv run pytest`). Contra a stack: `uv run python -m eval copy-corpus` e `uv run python -m eval run --help`.

**Leia também**: [scripts/AGENTS.md](../AGENTS.md); [docs/specs/avaliacao.md](../../docs/specs/avaliacao.md); o guia [docs/guias/avaliar-respostas.md](../../docs/guias/avaliar-respostas.md) (stack isolada, `run`, relatório e `compare`); [docs/specs/api-publica.md](../../docs/specs/api-publica.md).
