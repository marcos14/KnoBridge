# backend/src/knobridge/products/

**Função**: produtos do workspace, o sistema sobre o qual as pessoas perguntam ([produtos-e-niveis.md](../../../../docs/specs/produtos-e-niveis.md), [ADR 0008](../../../../docs/adr/0008-produtos-e-niveis.md)). Substitui `assistants/`: a migração `0018` transformou cada assistente num produto com o mesmo id.

**Entra aqui**:
- `models.py`: `Product` (tabela `products`; RLS forçada com políticas separadas de leitura, inserção, alteração e exclusão; nome sem `:<nível>` no fim, `ck_products_name_without_level`; `instructions`, o texto extra do produto; idioma, tom, mensagem de "sem fonte", `active`, `min_similarity` e o webhook de pedido de chamado), `ProductCollection` (tabela `product_collections`, N:N com `collections`, chave `(product_id, collection_id)`), `ProductTone` e as constantes `DEFAULT_NO_SOURCE_MESSAGE`, `DEFAULT_LANGUAGE`, `DEFAULT_MIN_SIMILARITY` (0,35), `MIN_SIMILARITY`/`MAX_SIMILARITY`, `TICKET_WEBHOOK_URL_MAX_LENGTH` e `NAME_LEVEL_SUFFIX_PATTERN`.
- Depois (plano 0009, F2.1): serviço, listagem e duplicação de produtos, que hoje ainda vivem em `assistants/`.

**Transitório (plano 0009)**: `Product.credential_id`, `model` e `temperature` são as colunas do assistente de origem, que o chat e o serviço de assistentes ainda leem até o chat ler o nível ([`levels/`](../levels/AGENTS.md)); saem numa migração seguinte do plano. Os sinônimos `Product.system_prompt` (→ `instructions`) e `ProductCollection.assistant_id` (→ `product_id`) existem só para o código de `assistants/` continuar funcionando; código novo usa os nomes novos. `assistants/models.py` reexporta estes modelos como `Assistant`, `AssistantCollection` e `AssistantTone`.

**Não entra aqui**: níveis do workspace e por membro (`levels/`), routers e schemas (`api/`), conversas (`conversations/`), pedidos de chamado (`tickets/`), migrações (`backend/migrations/`).

**Convenções locais**:
- Referências ao produto são compostas, `(workspace_id, product_id)` → `products (workspace_id, id)` (`uq_products_workspace_id_id`), com `ON DELETE CASCADE` em conversas, coleções do produto, níveis dos membros e pedidos de chamado.
- O segredo do webhook continua com os dados associados `assistant_ticket_webhook:<workspace_id>:<id>` (o id se preservou na `0018`).
- Toda consulta filtra por `workspace_id` e roda no escopo de RLS do workspace ([ADR 0001](../../../../docs/adr/0001-tenancy-e-rls.md)). Mudou modelo: migração nova e [modelo de dados](../../../../docs/specs/modelo-de-dados.md) na mesma entrega.

**Como testar**: de `backend/`, `uv run pytest tests/assistants tests/levels tests/migrations` (Postgres real; exige Docker). Gate da suíte inteira: `uv run pytest`.

**Leia também**: [assistants/AGENTS.md](../assistants/AGENTS.md); [levels/AGENTS.md](../levels/AGENTS.md); [docs/specs/modelo-de-dados.md](../../../../docs/specs/modelo-de-dados.md#products).
