# backend/src/knobridge/levels/

**Função**: níveis de resposta ([produtos-e-niveis.md](../../../../docs/specs/produtos-e-niveis.md), [ADR 0008](../../../../docs/adr/0008-produtos-e-niveis.md)): os três níveis, a configuração de cada nível no workspace e o nível máximo de cada membro em cada produto.

**Entra aqui**:
- `level.py`: `ResponseLevel` (`end_user`, `support`, `product_dev`, nessa ordem), `level_rank` e as constantes de temperatura (`MIN_TEMPERATURE`, `MAX_TEMPERATURE`, `DEFAULT_TEMPERATURE` = 0,2). Não importa nenhum outro módulo do pacote: `ingestion/`, `conversations/`, `apikeys/` e `products/` gravam um nível.
- `models.py`: `WorkspaceLevel` (tabela `workspace_levels`, chave `(workspace_id, level)`: credencial e modelo, os dois nulos ou os dois presentes, `ck_workspace_levels_model_with_credential`; temperatura; `instructions` nulo = texto padrão), `MemberProductLevel` (tabela `member_product_levels`, chave `(product_id, user_id)`: o nível máximo gravado por um admin; sem linha, vale o padrão do papel) e `create_workspace_levels(db, workspace_id)`, os três níveis sem modelo de um workspace novo, chamado pelo setup inicial e pela criação de workspace do superadmin (`tenancy/`).
- Depois (plano 0009, F2.1 e F2.2): os textos padrão (`defaults.py`), o serviço da configuração, o nível efetivo do membro e a regra do canal público (`policy.py`).

**Não entra aqui**: produtos (`products/`), routers e schemas (`api/`), o filtro de nível na busca (`retrieval/`), migrações (`backend/migrations/`).

**Convenções locais**:
- Duas tabelas de workspace com RLS forçada e a política padrão. FKs compostas: `(workspace_id, credential_id)` → `provider_credentials` (`NO ACTION`: credencial em uso por um nível não se exclui), `(workspace_id, product_id)` → `products` e `(workspace_id, user_id)` → `memberships` (`CASCADE`: excluir o produto ou a membership apaga o nível gravado).
- Todo workspace tem exatamente três `WorkspaceLevel`: quem cria workspace chama `create_workspace_levels` na mesma transação.
- Toda consulta filtra por `workspace_id` e roda no escopo de RLS do workspace ([ADR 0001](../../../../docs/adr/0001-tenancy-e-rls.md)). Mudou modelo: migração nova e [modelo de dados](../../../../docs/specs/modelo-de-dados.md) na mesma entrega.

**Como testar**: de `backend/`, `uv run pytest tests/levels` (Postgres real; exige Docker). Gate da suíte inteira: `uv run pytest`.

**Leia também**: [products/AGENTS.md](../products/AGENTS.md); [tests/levels/AGENTS.md](../../../tests/levels/AGENTS.md).
