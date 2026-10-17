# scripts/

**Função**: automação do repositório: as checagens que a CI roda além dos gates de cada pacote, a geração de dados sintéticos e as peças falsas que o E2E da stack sobe. É um projeto Python próprio (`knobridge-scripts`, gerenciado por `uv`), separado do backend para não misturar dependências.

**Entra aqui**:
- `check_agents_md.py`: falha se alguma pasta não tiver `AGENTS.md` (regra da seção 4 do [AGENTS.md da raiz](../AGENTS.md)).
- `check_plans.py`: valida o frontmatter de `docs/planos/NNNN-slug.md` contra o [modelo](../docs/planos/0000-modelo.md).
- `synthetic_tickets/`: gerador determinístico de chamados sintéticos em pt-BR, com gabarito da anonimização, artigos e perguntas (`uv run python -m synthetic_tickets --seed N --tickets 300 --out <pasta fora do repo>`; [AGENTS.md](synthetic_tickets/AGENTS.md)).
- `webhook_sink.py`: sistema de chamados falso do E2E (só biblioteca padrão): confere a `KnoBridge-Signature` com o segredo recebido em `PUT /secret`, responde `{ticket_id, url}` em `POST /hook` e lista o que chegou em `GET /deliveries` (com a pergunta, o canal e o solicitante de cada pedido assinado). O `docker-compose.e2e.yml` o monta numa imagem Python pequena (serviço `webhook-sink`).
- `fake_reranker.py`: reranker falso do E2E (só biblioteca padrão), na rota `POST /rerank` do TEI ([indexacao.md](../docs/specs/indexacao.md#e2e-e-testes)): pontua cada texto pela fração das palavras da consulta (minúsculas, sem acento) presentes nele, dá 1,0 ao texto com o marcador `[[rerank-top]]` e devolve `[{index, score}]` da maior para a menor, empate pela ordem de entrada; `GET /health` para o healthcheck. O `docker-compose.e2e.yml` o monta no lugar da imagem do TEI (serviço `reranker`).
- Outros scripts de checagem ou geração de código usados pela CI ou pelos hooks, cada um com testes em `tests/`.

**Não entra aqui**: código do produto (`backend/`, `frontend/`, `widget/`), infraestrutura (`deploy/`), workflows de CI (`.github/workflows/`), documentação (`docs/`).

**Convenções locais**:
- Um script por arquivo `check_*.py` (ou nome equivalente), sem dependência entre eles, executável com `uv run python <script>.py`.
- Todo script expõe `main(argv: list[str] | None = None) -> int` e devolve o código de saída: 0 ok, 1 problema encontrado, 2 entrada inválida. Só o bloco `__main__` chama `sys.exit`.
- Scripts são CLI: escrever no stdout é permitido aqui (problemas um por linha, caminhos com `/`).
- Caminhos padrão são relativos à raiz do repositório (pai desta pasta), para funcionar de qualquer diretório.
- Testes montam árvores sintéticas em `tmp_path`; só os testes marcados com `repo` olham o repositório real.
- `webhook_sink.py` e `fake_reranker.py` só usam a biblioteca padrão e não importam os outros scripts: o compose de E2E os roda sozinhos, montados numa imagem `python` sem dependências.
- Dados gerados pelo `synthetic_tickets` ficam fora do repositório; o único exemplo versionado é o JSONL do E2E (`frontend/e2e/stack/fixtures/tickets/`).

**Como testar** (de dentro de `scripts/`):

```bash
uv sync
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run pytest            # inclui --cov --cov-branch --cov-fail-under=95
uv run pytest -m "not repo"   # só os testes sintéticos
uv run python check_agents_md.py && uv run python check_plans.py
```

**Leia também**: seções 3, 4 e 5 do [AGENTS.md da raiz](../AGENTS.md); [docs/planos/AGENTS.md](../docs/planos/AGENTS.md).
