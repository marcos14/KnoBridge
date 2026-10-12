# backend/src/knobridge/apikeys/

**Função**: chaves de API (`kbk_`) que abrem a API pública de um workspace a programas ([ADR 0007](../../../../docs/adr/0007-chaves-e-api-publica.md), contrato em [api-publica.md](../../../../docs/specs/api-publica.md)). Hoje só o modelo de dados (plano 0008, F1.2); geração, autenticação e gestão chegam nas subfases seguintes.

**Entra aqui**:
- `models.py`: `ApiKey` (`api_keys`: nome único no workspace, `key_prefix` `[a-z0-9]{8}` único na instância, `key_hash` SHA-256 hex da chave inteira, `assistant_ids` `uuid[]` opcional (nulo = todos os assistentes ativos; 1 a 100 ids, sem nulos), `created_by`, `last_used_at`, `revoked_at`), com RLS forçada e a política padrão de workspace; `REFERENCED_MODELS` (`Workspace`, `User`), para o metadata estar completo onde o modelo é usado sozinho.

**Não entra aqui**: routers e schemas (`api/`), a conversa da API e o motor do chat (`conversations/`), migrações (`backend/migrations/`).

**Convenções locais**:
- `conversations/` não importa este pacote: `conversations.api_key_id` aponta para `api_keys` pelo nome da tabela (FK composta `(workspace_id, api_key_id)`), e quem grava conversas carrega `ApiKey` (`api/conversations.py`, `REFERENCED_MODELS`).
- A chave nunca é gravada, logada nem auditada; só `key_prefix` e o hash. A busca pela chave roda em `system_session` só por `key_prefix`; o resto da requisição roda no escopo do workspace da chave, sem `app.user_id`.
- Chaves não são excluídas, só revogadas: a FK das conversas é sem ação e impede apagar uma chave com conversas.
- `assistant_ids` não tem FK: assistente excluído some do escopo sem erro; pertencer ao workspace e não repetir é regra da aplicação.
- Mudou modelo: migração nova e [modelo de dados](../../../../docs/specs/modelo-de-dados.md) na mesma entrega.

**Como testar**: de `backend/`, `uv run pytest tests/apikeys` (exige Docker). Gate da suíte inteira: `uv run pytest`.

**Leia também**: [tests/apikeys/AGENTS.md](../../../tests/apikeys/AGENTS.md); [conversations/AGENTS.md](../conversations/AGENTS.md); [migrations/AGENTS.md](../../../migrations/AGENTS.md).
