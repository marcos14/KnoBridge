# backend/tests/conversations/

**Função**: testes de `src/knobridge/conversations/`: as partes puras do chat (prompt, título, citações, `NullRetriever`), o ciclo de vida do stream contra Postgres real (desconexão, cancelamento, `settle`) e o isolamento por RLS de `conversations`, `messages` e `feedback`.

**Entra aqui**: `test_prompt.py` (unitários, sem banco), `test_chat_stream.py` (`ChatService` com fakes de retriever e provedor: stream fechado ou cancelado vira `interrupted`, stream que nunca começou, desfecho gravado uma vez, conversa excluída no meio; e o comportamento dos fakes `UnreachableLLMProvider`/`ScriptedLLMProvider`), `test_conversations_rls.py` (RLS como dono e não dono via `rls_database_url`, FKs compostas) e `conversations_support.py` (`seed`: workspace, usuário, credencial `fake` cifrada, assistente e conversa pelos serviços; `run`; constantes). As regras pela API (papéis, SSE, regra 8, erros, histórico, feedback, auditoria) ficam em `tests/api/test_chat.py` e `tests/api/test_conversations.py`.
**Não entra aqui**: testes de rotas (`tests/api/`), da cadeia de migrações (`tests/migrations/`), chamadas a provedores reais.

**Convenções locais**:
- Os testes com banco levam `@pytest.mark.integration` e criam seus dados com valores únicos (banco compartilhado).
- Relógio `FrozenClock`; sem `sleep`: o provedor roteirizado espera num `asyncio.Event` (`hold_after`) para o teste desconectar no meio; o cancelamento usa um task group do anyio, como o Starlette.

**Como testar**: de `backend/`, `uv run pytest tests/conversations` (exige Docker).

**Leia também**: [conversations/AGENTS.md](../../src/knobridge/conversations/AGENTS.md); [tests/AGENTS.md](../AGENTS.md); [tests/fakes/AGENTS.md](../fakes/AGENTS.md).
