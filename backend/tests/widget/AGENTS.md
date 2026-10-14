# backend/tests/widget/

**Função**: testes de `src/knobridge/widget/` e do dono widget das conversas: RLS de `widgets` e `rate_limit_counters`, `CHECK`s e FKs, origens, chaves e o limitador de requisições com relógio congelado.

**Entra aqui**:
- `widget_support.py`: `run_db`, `new_widget` (widget sintético com chave pública nova) e `seed` (workspace novo com produto e widget).
- `conftest.py`: `rls_database_url` (o banco como dono e como não dono).
- `test_widget_rls.py`: RLS forçada nas duas tabelas, isolamento entre workspaces (leitura, alteração, exclusão e inserção alheia recusada), a chave pública achada só em modo de sistema e os contadores só em modo de sistema.
- `test_widget_constraints.py`: padrões da spec, cada `CHECK` de `widgets`, chave única na instância, nome único no workspace, produto de outro workspace recusado, cascata do produto e do widget até as conversas, os `CHECK`s da conversa do widget (dono único, token, identidade só com `sub`) e um feedback do visitante por mensagem.
- `test_widget_tables.py` (num interpretador novo): `Widget` sozinho e `Conversation` com `api/conversations.py` resolvem todas as FKs.
- `test_widget_origins.py` e `test_widget_keys.py` (unitários): normalização e cada motivo de origem inválida, curingas, origem da instância; formatos e cifra das chaves.
- `test_rate_limit.py`: janela que abre, soma, recusa com `Retry-After` (arredondado para cima), conta as recusadas e recomeça; contadores por widget e cliente; limpeza uma vez por hora; chave HMAC; IPv6 por `/64`.
- `test_widget_identity.py` (unitário): a identidade do exemplo reproduzível da spec (válida, `expired` 61 s depois de `exp`, `not_yet_valid` 61 s antes de `iat`, `signature` com o payload trocado ou outro segredo), `not_configured`, cada forma de `malformed` e de `claims`, `lifetime_too_long` e a tolerância configurável.
- `test_widget_visitor.py` (unitário): formato e hash do token `kbv_` e o cabeçalho `Authorization` (ausente, esquema, prefixo e tamanho errados: 401 com `WWW-Authenticate`).

**Não entra aqui**: rotas (`tests/api/test_widgets.py`, `tests/api/test_widget_public.py`, `tests/api/test_widget_conversations.py`, `tests/api/test_widget_tickets.py`, `tests/api/test_widget_admin_usage.py`), cadeia de migrações (`tests/migrations/`).

**Convenções locais**: testes com banco levam `@pytest.mark.integration` e criam dados únicos (banco compartilhado); preparo em `system_session`; relógio sempre `FrozenClock`.

**Como testar**: de `backend/`, `uv run pytest tests/widget` (exige Docker).

**Leia também**: [widget/AGENTS.md](../../src/knobridge/widget/AGENTS.md); [tests/AGENTS.md](../AGENTS.md).
