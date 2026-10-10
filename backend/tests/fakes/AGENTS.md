# backend/tests/fakes/

**Função**: implementações falsas das dependências externas, injetadas pelas mesmas interfaces (`Protocol`) que a produção usa, para nenhum teste chamar rede, LLM ou serviço de terceiros.

**Entra aqui**:
- `email_sender.py`: `FakeEmailSender` (implementa `EmailSender`; guarda as mensagens em `sent`, filtra com `sent_to(endereço)`).
- `llm_provider.py`: `FailingLLMProvider` (implementa `LLMProvider`; toda chamada levanta o `LLMProviderError` dado; `closed` diz se foi fechado), `UnreachableLLMProvider` (falha o teste se for chamado: prova que a resposta "sem fonte" não chama o LLM), `ScriptedLLMProvider` (deltas e uso roteirizados, grava cada chamada em `calls`; `error` + `fail_after` falha antes ou no meio do stream; `on_delta` avança o relógio; `hold_after` + `holding`/`release` (eventos asyncio) seguram o stream para o teste desconectar) e `RecordingFactory` (`ProviderFactory` que devolve o provedor dado e grava `FactoryCall(kind, api_key, base_url)`), para trocar `api.deps.get_provider_factory` via `dependency_overrides`. O fake de caminho feliz é produção (`knobridge.llm.fake.FakeLLMProvider`), porque o tipo `fake` o usa em dev e E2E.
- `retriever.py`: `StaticRetriever` (implementa `Retriever`; devolve as fontes dadas e grava cada consulta em `queries`), para trocar `api.deps.get_retriever`.
- Futuramente: fakes de `EmbeddingProvider`, `Reranker`, conectores e canais, um módulo por interface.

**Não entra aqui**: testes (`test_*.py` ficam na pasta do módulo testado), fixtures de dados (`tests/fixtures/`), servidores de protocolo de apoio usados por um único módulo de teste (ficam no `<subpasta>_support.py` da pasta, como o SMTP de `tests/email/`).

**Convenções locais**:
- Importe como `from fakes.<módulo> import ...` (o pytest põe `tests/` no `sys.path` por causa do `conftest.py` raiz).
- O fake implementa a interface inteira e é determinístico; o comportamento dele é coberto por um teste na pasta do módulo correspondente (ex.: `test_fake_sender_records_messages`).
- Sem dependência de rede, disco ou relógio real.

**Como testar**: de `backend/`, `uv run pytest` (os fakes são exercitados pelos testes que os usam).

**Leia também**: [tests/AGENTS.md](../AGENTS.md); seção 5 do [AGENTS.md da raiz](../../../AGENTS.md).
