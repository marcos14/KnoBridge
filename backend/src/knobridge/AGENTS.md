# backend/src/knobridge/

**Função**: pacote Python do KnoBridge. Cada subpasta é um módulo do produto (layout previsto em [backend/AGENTS.md](../../AGENTS.md)); hoje existem `core/`, `api/`, `tenancy/`, `security/`, `audit/`, `email/`, `llm/`, `assistants/`, `conversations/`, `ingestion/`, `harness/`, `tickets/`, `apikeys/`, `connectors/`, `retrieval/` e `workers/`.

**Entra aqui**:
- `__init__.py` com `__version__`, a única fonte da versão (o `pyproject.toml` lê daqui via hatch).
- Um subpacote por módulo do produto, cada um com o seu `AGENTS.md`.

**Não entra aqui**: testes (vão para `backend/tests/`, espelhando esta árvore), documentação (`docs/`), scripts de repositório (`scripts/`), módulos soltos na raiz do pacote além de `__init__.py`.

**Convenções locais**:
- Crie um subpacote só quando ele for necessário, sempre com `AGENTS.md` e testes em `tests/<subpacote>/`.
- Dependências entre módulos apontam para baixo: `api/` e `workers/` usam `core/` e os módulos de domínio; `core/` não importa nenhum outro módulo do pacote. Exceção deliberada: `api/` importa `workers/sync_client.py` (o `SyncStarter` sobre o Temporal), porque disparar sincronização é a única coisa que a API pede ao Temporal.
- `ingestion/` não importa `harness/` nem `tickets/`: a API e o worker passam as fábricas dos conectores internos (`KnowledgeConnectorFactory` e `TicketsConnectorFactory`, em `knowledge=` e `tickets=`) ao `SettingsConnectorFactory`; o teste de conexão da fonte `tickets` entra no `SourceService` como `ConnectionCheck` (`tickets.tokens.ingest_token_failure`), passado pela API.
- `api/conversations.py` importa `tickets/requests.py` (pedidos por mensagem e `ticket_requests_enabled`); `conversations/` não importa `tickets/`.
- `conversations/` não importa `apikeys/`: `conversations.api_key_id` aponta para `api_keys` pelo nome da tabela, e `api/conversations.py` carrega `ApiKey` (`REFERENCED_MODELS`) para o metadata estar completo onde se gravam conversas.
- Vocabulário do domínio da seção 6.1 do [AGENTS.md da raiz](../../../AGENTS.md) nos nomes.

**Como testar**: de `backend/`, `uv run pytest` (gate de 95% de linhas e branches) e `uv run pyright`.

**Leia também**: [core/AGENTS.md](core/AGENTS.md), [tenancy/AGENTS.md](tenancy/AGENTS.md), [security/AGENTS.md](security/AGENTS.md), [audit/AGENTS.md](audit/AGENTS.md), [email/AGENTS.md](email/AGENTS.md), [llm/AGENTS.md](llm/AGENTS.md), [assistants/AGENTS.md](assistants/AGENTS.md), [conversations/AGENTS.md](conversations/AGENTS.md), [ingestion/AGENTS.md](ingestion/AGENTS.md), [harness/AGENTS.md](harness/AGENTS.md), [tickets/AGENTS.md](tickets/AGENTS.md), [apikeys/AGENTS.md](apikeys/AGENTS.md), [connectors/AGENTS.md](connectors/AGENTS.md) (com [connectors/folder/](connectors/folder/AGENTS.md) e [connectors/git/](connectors/git/AGENTS.md)), [retrieval/AGENTS.md](retrieval/AGENTS.md), [api/AGENTS.md](api/AGENTS.md), [workers/AGENTS.md](workers/AGENTS.md).
