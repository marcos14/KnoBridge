# backend/src/knobridge/conversations/

**Função**: o motor do chat. Histórico de conversas (conversa, mensagens, feedback), a interface `Retriever` que busca as fontes de uma resposta e a orquestração de uma rodada de pergunta e resposta em streaming, que garante a regra 8 do [AGENTS.md da raiz](../../../../AGENTS.md): sem fonte, a resposta é a mensagem de "sem fonte" do assistente e o LLM não é chamado.

**Entra aqui**:
- `models.py`: `Conversation` (assistente, dono, título, canal `panel`), `Message` (`position`, papel, conteúdo, `citations` JSONB, `status`, `error_code`, modelo, tokens, latência) e `Feedback` (`up`/`down` + comentário, um por mensagem e usuário), com RLS forçada e FKs compostas `(workspace_id, <pai>_id)`; enums `ConversationChannel`, `MessageRole`, `MessageStatus` (`streaming`, `completed`, `no_source`, `failed`, `interrupted`), `FeedbackRating`.
- `retrieval.py`: `Retriever` (`Protocol`), `RetrievalQuery` (workspace, assistente, usuário para ACL, texto), `Source`, `NullRetriever` (produção até existir indexação: nada encontrado, toda resposta é "sem fonte") e `citation()` (JSON gravado: `index`, `title`, `uri`, `snippet` de 300 caracteres, `document_id`).
- `prompt.py`: funções puras: instruções (prompt do assistente + regras de citação `[n]`, idioma, tom e a mensagem de "sem fonte"), fontes numeradas, mensagens para o LLM e `title_from_question` (80 caracteres, sem LLM).
- `service.py`: `ConversationService` (criar com assistente ativo, listar as minhas, ler, listar mensagens com o feedback de quem lê, excluir auditando `conversation.deleted`, upsert de feedback) e as regras de acesso `Reader`, `get_readable_conversation`, `require_owner`, `get_active_assistant`; erros `AssistantInactiveError` 409 e `FeedbackTargetInvalidError` 422.
- `turn.py`: os dados de uma rodada: `PreparedTurn`, `LLMCall`, os eventos `CitationsEvent`, `DeltaEvent`, `DoneEvent`, `ErrorEvent` (`ChatEvent`) e `ChatFailedError` (`chat_failed`).
- `chat.py`: `ChatService` com `prepare` (fase 1), `stream` (fase 2) e `settle`.
- Sem routers (a API fica em `api/conversations.py`; contrato dos eventos em [docs/specs/chat-sse.md](../../../../docs/specs/chat-sse.md)).

**Não entra aqui**: busca híbrida, reranker e montagem de contexto de verdade (`retrieval/`, quando existir, implementando `Retriever`), adaptadores de LLM (`llm/`), configuração do assistente (`assistants/`), canais externos (`channels/`), routers e schemas (`api/`).

**Convenções locais**:
- **Sessão de banco no streaming**: a rodada tem duas fases para não segurar transação aberta enquanto o LLM responde. `prepare` roda na sessão do `WorkspaceContext` (a transação da requisição, que faz commit antes de a resposta começar): trava a conversa (`FOR UPDATE`, posições únicas), grava a pergunta, chama o retriever e grava a resposta: final (`no_source`) ou um marcador `streaming` com as citações. `stream` chama o provedor fora de qualquer transação e grava o desfecho num `scoped_session` novo, curto, no fim. Assim a conexão volta ao pool durante a geração (que leva segundos) e o padrão "um `scoped_session` por transação, sem reaproveitar depois do commit" de `core/db.py` é respeitado.
- O desfecho é gravado uma vez só: o `UPDATE` só pega mensagem ainda `streaming` (conversa excluída no meio simplesmente não casa). A gravação final fica num `anyio.CancelScope(shield=True)`, porque na desconexão do cliente o Starlette cancela a tarefa; `GeneratorExit`/cancelamento viram `interrupted` com o conteúdo parcial. `settle` cobre o stream que nunca começou (o `ChatEventStream` da API sempre o chama ao fechar).
- O provedor só é construído quando o stream começa (`LLMCall.open_provider`) e é sempre fechado; a chave é decifrada só em memória. Erro de domínio do provedor vira evento `error` com o código dele; qualquer outra exceção vira `chat_failed`, registrada só pelo tipo (o texto pode conter a chave).
- Histórico: as 10 mensagens mais recentes (`DEFAULT_HISTORY_WINDOW`), só perguntas e respostas `completed`/`no_source`.
- Latência pelo `Clock` injetado. Logs (`chat_turn_finished`, `chat_turn_crashed`) com `workspace_id` e `conversation_id`, sem pergunta nem resposta.
- Toda consulta filtra por `workspace_id` e roda no escopo de RLS ([ADR 0001](../../../../docs/adr/0001-tenancy-e-rls.md)); a privacidade entre membros é regra da aplicação. Mudou modelo: migração nova e [modelo de dados](../../../../docs/specs/modelo-de-dados.md).

**Como testar**: de `backend/`, `uv run pytest tests/conversations tests/api/test_chat.py tests/api/test_conversations.py` (Postgres real; exige Docker). Gate da suíte inteira: `uv run pytest`.

**Leia também**: [tests/conversations/AGENTS.md](../../../tests/conversations/AGENTS.md); [llm/AGENTS.md](../llm/AGENTS.md); [assistants/AGENTS.md](../assistants/AGENTS.md); seções 7.4 e 7.5 da [visão](../../../../docs/01-visao-do-projeto.md).
