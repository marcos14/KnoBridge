# backend/tests/fakes/

**Função**: implementações falsas das dependências externas, injetadas pelas mesmas interfaces (`Protocol`) que a produção usa, para nenhum teste chamar rede, LLM ou serviço de terceiros.

**Entra aqui**:
- `email_sender.py`: `FakeEmailSender` (implementa `EmailSender`; guarda as mensagens em `sent`, filtra com `sent_to(endereço)`).
- `llm_provider.py`: `FailingLLMProvider` (implementa `LLMProvider`; toda chamada levanta o `LLMProviderError` dado; `closed` diz se foi fechado), `UnreachableLLMProvider` (falha o teste se for chamado: prova que a resposta "sem fonte" não chama o LLM), `ScriptedLLMProvider` (deltas e uso roteirizados, grava cada chamada em `calls`; `error` + `fail_after` falha antes ou no meio do stream; `on_delta` avança o relógio; `hold_after` + `holding`/`release` (eventos asyncio) seguram o stream para o teste desconectar) e `RecordingFactory` (`ProviderFactory` que devolve o provedor dado e grava `FactoryCall(kind, api_key, base_url)`), para trocar `api.deps.get_provider_factory` via `dependency_overrides`. O fake de caminho feliz é produção (`knobridge.llm.fake.FakeLLMProvider`), porque o tipo `fake` o usa em dev e E2E.
- `retriever.py`: `StaticRetriever` (implementa `Retriever`, `retrieve(db, query)`; devolve as fontes dadas e grava cada consulta em `queries`), para trocar `api.deps.get_retriever` quando o teste não precisa do índice (o retriever real é testado em `tests/retrieval/test_retriever.py` e `tests/api/test_chat_retrieval.py`).
- `connector.py`: `FakeConnector` (implementa `Connector` em memória: `files` chave → bytes, `put`/`delete`, `available = False` quebra a fonte; cursor `{"fake": {chave: sha256}}`), a referência da suíte de contrato de `tests/connectors/contract/`.
- O fake de caminho feliz de `EmbeddingProvider` também é produção (`knobridge.llm.fake_embeddings.FakeEmbeddingProvider`, usado pelo tipo `fake`).
- `embedding_provider.py`: `RecordingEmbeddingProvider` (implementa `EmbeddingProvider` delegando ao `FakeEmbeddingProvider`; grava `texts`, `models`, `calls` e `closed`; `error` faz cada chamada falhar, ou só as próximas `fail_times`) e `RecordingEmbeddingFactory` (`EmbeddingProviderFactory` que devolve sempre o seu `provider` e grava `EmbeddingFactoryCall(kind, api_key, base_url)`), usados pelos testes de ingestão, de busca e do chat (trocar `api.deps.get_embedding_provider_factory` ou passar ao `SearchService`).
- `sync_starter.py`: `FakeSyncStarter` (implementa `SyncStarter`; grava `started` (`StartCall`) e `cancelled`; fonte iniciada fica em `running` até `cancel` ou `finish`, segunda partida dá `SyncAlreadyRunningError`, cancelar sem execução dá `SyncNotRunningError`; `unavailable = True` faz toda chamada levantar `SyncUnavailableError`), para trocar `api.deps.get_sync_starter`.
- Futuramente: fakes de `Reranker` e canais quando um teste precisar, um módulo por interface.

**Não entra aqui**: testes (`test_*.py` ficam na pasta do módulo testado), fixtures de dados (`tests/fixtures/`), servidores de protocolo de apoio usados por um único módulo de teste (ficam no `<subpasta>_support.py` da pasta, como o SMTP de `tests/email/`).

**Convenções locais**:
- Importe como `from fakes.<módulo> import ...` (o pytest põe `tests/` no `sys.path` por causa do `conftest.py` raiz).
- O fake implementa a interface inteira e é determinístico; o comportamento dele é coberto por um teste na pasta do módulo correspondente (ex.: `test_fake_sender_records_messages`).
- Sem dependência de rede, disco ou relógio real.

**Como testar**: de `backend/`, `uv run pytest` (os fakes são exercitados pelos testes que os usam).

**Leia também**: [tests/AGENTS.md](../AGENTS.md); seção 5 do [AGENTS.md da raiz](../../../AGENTS.md).
