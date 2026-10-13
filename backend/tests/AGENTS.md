# backend/tests/

**Função**: testes do backend, espelhando `src/knobridge/` (`tests/core/` testa `knobridge/core/`, e assim por diante).

**Entra aqui**:
- `conftest.py` com as fixtures compartilhadas: `settings` (configuração de teste), `app` e `client` (TestClient sobre `create_app`), `postgres_url` (sessão inteira: DSN asyncpg de um container `pgvector/pgvector:pg17` via testcontainers, como superusuário), `app_database_url` (sessão inteira: banco próprio migrado até `head`, conectando como o papel de aplicação dono e não superusuário, igual ao deploy, para a RLS valer), `non_owner_database_url` (o mesmo banco como papel não dono, só com privilégios de tabela), `empty_database_url` (por teste: banco novo, migrado e vazio, do papel de aplicação; para o setup inicial, que exige nenhum usuário; use com parcimônia), e uma fixture automática que isola o estado global (variáveis `KNOBRIDGE_*` do host, `.env` local, cache de settings, configuração de logging).
- Uma subpasta por módulo de `src/knobridge/`, com o seu `AGENTS.md` (hoje `core/`, `api/`, `tenancy/`, `security/`, `audit/`, `email/`, `llm/`, `assistants/`, `conversations/`, `ingestion/`, `connectors/`, `retrieval/`, `workers/`, `harness/`, `tickets/`, `apikeys/`, `usage/`), e `migrations/` para a cadeia do Alembic. Helpers compartilhados de uma subpasta ficam num módulo `<subpasta>_support.py` (nome único, importado pelo basename).
- `fakes/`: implementações falsas das interfaces externas, importadas como `fakes.<módulo>` (hoje `FakeEmailSender`, fakes de `LLMProvider`, o `StaticRetriever`, o `FakeConnector` e fakes de `EmbeddingProvider`; depois reranker).
- `fixtures/`: dados sintéticos e pequenos, só dados (sem `AGENTS.md`, seção 4 do AGENTS.md raiz); hoje `fixtures/documents/` com um PDF, um DOCX, um XLSX e um PPTX mínimos para o parsing, e `fixtures/tickets/` com os exemplos válido e inválido de chamado da spec de chamados. Leia com caminho relativo a `__file__` (o cwd do teste é `tmp_path`).

**Não entra aqui**: código de produção, dados reais de clientes, chamadas de rede reais, testes de `scripts/` (ficam em `scripts/tests/`).

**Convenções locais**:
- Nome `test_<unidade>_<comportamento>`, arrange / act / assert, um comportamento por teste.
- Sem rede, sem `sleep`, sem hora real, sem aleatoriedade sem seed. LLM e APIs externas só por fakes.
- A fixture automática muda o cwd para `tmp_path`: crie ali o `.env` quando o teste precisar de um.
- Testes que precisam de Postgres ou Temporal reais levam `@pytest.mark.integration` e rodam por padrão (Postgres exige Docker; Temporal usa o servidor de teste do SDK, baixado na primeira execução; ver `workers/AGENTS.md`). Postgres: use a fixture `postgres_url`; crie o engine dentro do loop do teste (`asyncio.run` ou `TestClient`) com `NullPool` ou descarte-o no fim. Quem altera o schema devolve o banco a `base`, porque o container é compartilhado. Testes de dados e de isolamento usam `app_database_url` (nunca o superusuário de `postgres_url`, que ignora RLS) e criam dados com valores únicos, porque esse banco também é compartilhado.
- Pytest roda sem pacotes (`tests/` não tem `__init__.py`): basenames de arquivos de teste precisam ser únicos em toda a árvore.

**Como testar**: de `backend/`, `uv run pytest` (cobertura de linhas e branches com `--cov-fail-under=95`); só unitários: `uv run pytest -m "not integration"`.

**Leia também**: seção 5 do [AGENTS.md da raiz](../../AGENTS.md); [backend/AGENTS.md](../AGENTS.md).
