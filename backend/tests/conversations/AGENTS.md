# backend/tests/conversations/

**Função**: testes de `src/knobridge/conversations/`: as partes puras do chat (prompt com as regras fixas em pt-BR, título, citações com os campos de localização), o ciclo de vida do stream contra Postgres real (desconexão, cancelamento, `settle`) e o isolamento por RLS de `conversations`, `messages` e `feedback`.

**Entra aqui**: `test_prompt.py` e `test_tools.py` (unitários, sem banco), `test_chat_steps.py` e `test_chat_steps_edges.py` (busca em etapas no `ChatService` com Postgres real: 1, 2 e N etapas, o máximo do nível, regra 8 sem fonte (com a busca inicial vazia, `tool_choice` `auto` e a linha `NO_SOURCES_YET`; texto do modelo sem fonte vira a resposta de sem fonte), recusa de ferramentas, chamadas inválidas e paralelas, limite de fontes, busca que falha, prazo da resposta e erros numa rodada de busca), com `steps_support.py` (o chat sobre o `StaticRetriever` com fontes por consulta, preços de teste, o nível e uma rodada inteira), `test_chat_stream.py` (`ChatService` com fakes de retriever e provedor: stream fechado ou cancelado vira `interrupted`, stream que nunca começou, desfecho gravado uma vez, conversa excluída no meio; e o comportamento dos fakes `UnreachableLLMProvider`/`ScriptedLLMProvider`), `test_conversations_rls.py` (RLS como dono e não dono via `rls_database_url`, FKs compostas) e `conversations_support.py` (`seed`: workspace, usuário, credencial `fake` cifrada nos três níveis, produto e conversa pelos serviços; `run`; constantes). As regras pela API (papéis, SSE, regra 8, erros, histórico, feedback, auditoria) ficam em `tests/api/test_chat.py` e `tests/api/test_conversations.py`.
**Não entra aqui**: testes de rotas (`tests/api/`), da cadeia de migrações (`tests/migrations/`), chamadas a provedores reais.

**Convenções locais**:
- Os testes com banco levam `@pytest.mark.integration` e criam seus dados com valores únicos (banco compartilhado).
- Relógio `FrozenClock`; sem `sleep`: o provedor roteirizado espera num `asyncio.Event` (`hold_after`) para o teste desconectar no meio; o cancelamento usa um task group do anyio, como o Starlette.

**Como testar**: de `backend/`, `uv run pytest tests/conversations` (exige Docker).

**Leia também**: [conversations/AGENTS.md](../../src/knobridge/conversations/AGENTS.md); [tests/AGENTS.md](../AGENTS.md); [tests/fakes/AGENTS.md](../fakes/AGENTS.md).
