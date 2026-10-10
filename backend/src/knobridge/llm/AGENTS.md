# backend/src/knobridge/llm/

**Função**: provedores de LLM. As credenciais por workspace (chave de API cifrada em repouso), a interface `LLMProvider` com os adaptadores sobre os SDKs oficiais (OpenAI, Anthropic, OpenRouter) e o provedor determinístico `fake`. Depois, `EmbeddingProvider`, `Reranker` e a assinatura via Codex, conforme o layout de [backend/AGENTS.md](../../../AGENTS.md). Sem framework de LLM (decisão D6 da visão): SDK oficial + esta interface pequena.

**Entra aqui**:
- `models.py`: `ProviderCredential` (tabela `provider_credentials`; RLS forçada, política padrão de workspace) e `ProviderKind` (`openai`, `anthropic`, `openrouter`, `fake`).
- `credentials.py`: `ProviderCredentialService(clock, box, allow_fake=)` com `list_credentials` (por nome, paginado), `create`, `update` (nome, `base_url` (`None` limpa quando informado), troca da chave; o tipo não muda), `delete` e `test_connection` (decifra a chave só em memória, chama `check_connection` do adaptador, fecha o adaptador e audita `provider.tested` com `ok` e `error_code`; devolve a falha em vez de levantar, para a auditoria ser gravada também no erro), todos na sessão do `WorkspaceContext` e auditados (`provider.created`, `provider.updated`, `provider.deleted`, `provider.tested`); `reveal_key` (texto em claro só para chamar o provedor); `masked_key` (`****1234`); `CREDENTIALS_KEY_INFO`; erros `ProviderNameTakenError` 409 e `ProviderKindNotAllowedError` 422 (`fake` em produção).
- `provider.py`: `LLMProvider` (`Protocol`: `stream_chat(messages, model, params)` gera `TextDelta` e termina sempre com um `ChatUsage` (tokens ou `None` se o provedor não informou); `list_models()`; `check_connection()`, a chamada autenticada mais barata; `aclose()`), `ChatMessage`, `ChatRole`, `ChatParams` (`temperature`, `max_tokens`).
- `openai_adapter.py`: `OpenAIProvider` (SDK `openai`; `base_url` para servidores compatíveis como Ollama e vLLM; `max_completion_tokens`) e `OpenRouterProvider` (mesmo SDK com `OPENROUTER_BASE_URL` por padrão; `max_tokens`; `check_connection` em `GET /key`, porque `/models` lá é público). `anthropic_adapter.py`: `AnthropicProvider` (SDK `anthropic`; mensagens de sistema vão para `system`; `max_tokens` padrão `DEFAULT_MAX_TOKENS`; `temperature` via `extra_body`, porque o SDK não o tipa mais).
- `errors.py`: `LLMProviderError` (`KnoBridgeError`, `details` = `{provider, status}`) e as subclasses `ProviderAuthError` (`provider_auth_failed`, 401/403 do provedor), `ProviderRateLimitError` (`provider_rate_limited`, 429), `ProviderUnavailableError` (`provider_unavailable`, 5xx, rede ou timeout) e `ProviderRequestError` (`provider_request_failed`, demais 4xx); `error_for_status` e `connection_error`.
- `fake.py`: `FakeLLMProvider`, determinístico (ecoa a última mensagem do usuário em deltas por palavra, tokens contados por palavra; sem rede, relógio ou aleatoriedade); usado pelo tipo `fake` e nos testes.
- `factory.py`: `ProviderFactory` (`Protocol`) e `create_provider(kind, api_key=, base_url=, timeout=60, max_retries=2, http_client=None)`. A API recebe a fábrica por dependência (`api/deps.get_provider_factory`), que os testes trocam.
- Sem routers (a API fica em `api/providers.py`).

**Não entra aqui**: a primitiva de cifra (`core/crypto.py`), routers e schemas (`api/`), migrações (`backend/migrations/`), LangChain/LlamaIndex ou outro framework de LLM, chamadas reais a provedores em teste (use `FakeLLMProvider`, os fakes de `tests/fakes/` ou `httpx2.MockTransport` no cliente do SDK).

**Convenções locais**:
- A chave nunca sai em resposta de API, log ou metadado de auditoria; só `key_last4` para exibição. A cifra usa `SecretBox` com `info` próprio (`CREDENTIALS_KEY_INFO`) e dados associados `provider_credential:<workspace_id>:<id>` (o id é gerado antes de cifrar). Regras no [ADR 0003](../../../../docs/adr/0003-segredos-cifrados.md).
- Adaptadores nunca deixam escapar exceção do SDK: traduzem por status HTTP para `errors.py`, com mensagem própria e `from None` (a mensagem do provedor pode ecoar parte da chave). Nenhum erro usa 401, que o painel entende como sessão expirada.
- Adaptador novo: implementa `LLMProvider` inteiro, recebe `timeout`, `max_retries` e `http_client` (para os testes injetarem transporte fake) e entra em `create_provider`.
- Toda consulta filtra por `workspace_id` e roda no escopo de RLS do workspace ([ADR 0001](../../../../docs/adr/0001-tenancy-e-rls.md)).
- Assistentes (F4.3) referenciam credenciais com `ON DELETE RESTRICT`.
- Mudou modelo: migração nova e [modelo de dados](../../../../docs/specs/modelo-de-dados.md) na mesma entrega.

**Como testar**: de `backend/`, `uv run pytest tests/llm tests/api/test_providers.py tests/api/test_provider_connection.py` (os de credenciais usam Postgres real; exige Docker). Gate da suíte inteira: `uv run pytest`.

**Leia também**: [ADR 0003](../../../../docs/adr/0003-segredos-cifrados.md); seções 7.5 e 8 da [visão](../../../../docs/01-visao-do-projeto.md); [core/AGENTS.md](../core/AGENTS.md); [tests/llm/AGENTS.md](../../../tests/llm/AGENTS.md).
