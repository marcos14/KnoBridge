# backend/src/knobridge/assistants/

**Função**: assistentes do workspace (seção 7.5 da [visão](../../../../docs/01-visao-do-projeto.md)). Hoje, só a configuração: prompt de sistema, credencial de provedor e modelo, temperatura, idioma, tom, mensagem de "sem fonte" e `active`. Depois, a orquestração da conversa, as ferramentas (ações) e a memória, conforme o layout de [backend/AGENTS.md](../../../AGENTS.md).

**Entra aqui**:
- `models.py`: `Assistant` (tabela `assistants`; RLS forçada com políticas separadas de leitura, inserção, alteração e exclusão), `AssistantTone` (`neutral`, `formal`, `friendly`) e as constantes `DEFAULT_NO_SOURCE_MESSAGE` (pt-BR: diz que não sabe e oferece abrir chamado), `DEFAULT_TEMPERATURE` (0,2), `MIN_TEMPERATURE`/`MAX_TEMPERATURE` (0 a 2) e `DEFAULT_LANGUAGE` (`pt-BR`).
- `service.py`: `AssistantService(clock)` com `list_assistants` (por nome, paginado, `active_only` para viewer), `get`, `create` (`AssistantSettings`), `update` (`AssistantChanges`; `None` mantém, audita só o que mudou) e `delete`, todos na sessão do `WorkspaceContext` e auditados (`assistant.created`, `assistant.updated` com `fields`, `assistant.deleted`); erros `AssistantNameTakenError` 409 e `AssistantProviderInvalidError` 422.
- Sem routers (a API fica em `api/assistants.py`).

**Não entra aqui**: credenciais e adaptadores de LLM (`llm/`), routers e schemas (`api/`), migrações (`backend/migrations/`), recuperação e montagem de contexto (`retrieval/`), canais (`channels/`).

**Convenções locais**:
- A credencial é sempre do mesmo workspace: o serviço a procura com filtro de workspace (e RLS) e a trava com `FOR KEY SHARE` até o commit; a FK composta `(workspace_id, credential_id)` → `provider_credentials (workspace_id, id)` é a última barreira. `NO ACTION` na exclusão: credencial em uso não se exclui (`provider_in_use`), e excluir o workspace ainda cascateia para as duas tabelas.
- Mensagem de "sem fonte" vazia (ou nula na API) grava `DEFAULT_NO_SOURCE_MESSAGE` (regra 8 do [AGENTS.md da raiz](../../../../AGENTS.md)); a coluna nunca fica vazia.
- Auditoria sem prompt nem mensagem: só nome, modelo, id do provedor e campos alterados (nomes da API: `provider_id`).
- Toda consulta filtra por `workspace_id` e roda no escopo de RLS do workspace ([ADR 0001](../../../../docs/adr/0001-tenancy-e-rls.md)).
- Mudou modelo: migração nova e [modelo de dados](../../../../docs/specs/modelo-de-dados.md) na mesma entrega.

**Como testar**: de `backend/`, `uv run pytest tests/assistants tests/api/test_assistants.py` (Postgres real; exige Docker). Gate da suíte inteira: `uv run pytest`.

**Leia também**: [llm/AGENTS.md](../llm/AGENTS.md); [api/AGENTS.md](../api/AGENTS.md); [tests/assistants/AGENTS.md](../../../tests/assistants/AGENTS.md).
