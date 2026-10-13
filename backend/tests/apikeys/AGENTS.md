# backend/tests/apikeys/

**Função**: testes de `src/knobridge/apikeys/` e das conversas que pertencem a uma chave, contra Postgres real: RLS de `api_keys`, busca pelo prefixo, chaves, `CHECK`s, FKs e o que as leituras do painel fazem com as conversas da API.

**Entra aqui**:
- `apikeys_support.py`: `run_db`, `new_key` (chave sintética com prefixo aleatório e o SHA-256), `api_conversation` e `seed` (workspace novo com usuário, assistente, chave com escopo nele e uma conversa da chave).
- `conftest.py`: `rls_database_url` (o banco como dono e como não dono).
- `test_api_keys_rls.py`: RLS forçada, isolamento entre workspaces (leitura, alteração, exclusão e inserção alheia recusada) e a chave achada pelo `key_prefix` só em modo de sistema.
- `test_api_keys_constraints.py`: padrões, prefixo único na instância, nome único no workspace (e repetido entre workspaces), cada `CHECK`, escopo de 100 assistentes, `created_by` anulado com o usuário, chave com conversas que não pode ser apagada e a cascata do workspace.
- `test_api_conversations.py`: um único dono por canal (os dois `CHECK`s de `conversations`), chave de outro workspace recusada pela FK composta, `messages.channel` (padrão `panel`, `api`, valor desconhecido) e `messages.cost_usd` (6 casas, negativo e em pergunta recusados); o detalhe do painel responde 404 e a lista administrativa pula a conversa da API (itens e total).
- `test_api_key_tokens.py` (unitário): formato, prefixo, aleatoriedade e conferência do hash das chaves `kbk_`.
- `test_api_key_tables.py` (unitário, num interpretador novo): `ApiKey` sozinho e `Conversation` com `api/conversations.py` resolvem todas as FKs.

**Não entra aqui**: rotas (`tests/api/`), cadeia de migrações (`tests/migrations/`).

**Convenções locais**: testes com banco levam `@pytest.mark.integration` e criam dados com valores únicos (banco compartilhado); RLS pelo `rls_database_url`, que roda como dono e como não dono; inserções de preparo em `system_session`.

**Como testar**: de `backend/`, `uv run pytest tests/apikeys` (exige Docker).

**Leia também**: [apikeys/AGENTS.md](../../src/knobridge/apikeys/AGENTS.md); [tests/AGENTS.md](../AGENTS.md).
