# backend/src/knobridge/llm/

**Função**: provedores de LLM. Hoje, as credenciais por workspace (chave de API cifrada em repouso). Depois, as interfaces `LLMProvider` / `EmbeddingProvider` / `Reranker` e os adaptadores (OpenAI, Anthropic, OpenRouter, assinatura via Codex), conforme o layout de [backend/AGENTS.md](../../../AGENTS.md).

**Entra aqui**:
- `models.py`: `ProviderCredential` (tabela `provider_credentials`; RLS forçada, política padrão de workspace) e `ProviderKind` (`openai`, `anthropic`, `openrouter`, `fake`).
- `credentials.py`: `ProviderCredentialService(clock, box, allow_fake=)` com `list_credentials` (por nome, paginado), `create`, `update` (nome, `base_url` (`None` limpa quando informado), troca da chave; o tipo não muda) e `delete`, todos na sessão do `WorkspaceContext` e auditados (`provider.created`, `provider.updated`, `provider.deleted`); `reveal_key` (texto em claro só para chamar o provedor); `masked_key` (`****1234`); `CREDENTIALS_KEY_INFO`; erros `ProviderNameTakenError` 409 e `ProviderKindNotAllowedError` 422 (`fake` em produção).
- Sem routers (a API fica em `api/providers.py`).

**Não entra aqui**: a primitiva de cifra (`core/crypto.py`), routers e schemas (`api/`), migrações (`backend/migrations/`), chamadas reais a provedores em teste (use fakes em `tests/fakes/`).

**Convenções locais**:
- A chave nunca sai em resposta de API, log ou metadado de auditoria; só `key_last4` para exibição. A cifra usa `SecretBox` com `info` próprio (`CREDENTIALS_KEY_INFO`) e dados associados `provider_credential:<workspace_id>:<id>` (o id é gerado antes de cifrar). Regras no [ADR 0003](../../../../docs/adr/0003-segredos-cifrados.md).
- Toda consulta filtra por `workspace_id` e roda no escopo de RLS do workspace ([ADR 0001](../../../../docs/adr/0001-tenancy-e-rls.md)).
- Assistentes (F4.3) referenciam credenciais com `ON DELETE RESTRICT`.
- Mudou modelo: migração nova e [modelo de dados](../../../../docs/specs/modelo-de-dados.md) na mesma entrega.

**Como testar**: de `backend/`, `uv run pytest tests/llm tests/api/test_providers.py` (Postgres real; exige Docker). Gate da suíte inteira: `uv run pytest`.

**Leia também**: [ADR 0003](../../../../docs/adr/0003-segredos-cifrados.md); [core/AGENTS.md](../core/AGENTS.md); [tests/llm/AGENTS.md](../../../tests/llm/AGENTS.md).
