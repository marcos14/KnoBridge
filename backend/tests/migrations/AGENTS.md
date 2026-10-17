# backend/tests/migrations/

**Função**: testes da cadeia de migrações Alembic de `backend/migrations/`.

**Entra aqui**: `test_migrations.py`, que roda `alembic upgrade` e `downgrade` programaticamente (`alembic.command`) contra o Postgres 17 + pgvector da fixture `postgres_url`, e confere o efeito no catálogo do banco (`pg_extension`, `pg_class.relrowsecurity`/`relforcerowsecurity`, `pg_policies`), além de `test_migrations_match_orm_models`, que compara o schema em `head` com `Base.metadata` (autogenerate sem diferenças). Desde a `0017`, migração nova ganha arquivo próprio (`test_migration_0017.py`: tabela, colunas e `CHECK`s depois do `upgrade`, ausentes depois do `downgrade`, e o `downgrade` recusado com conversa da API), porque `test_migrations.py` já passa do tamanho recomendado. `test_migration_0018.py` cria um banco por teste, dono o papel de aplicação (não superusuário, como no deploy), migra até `0017`, semeia assistentes, coleções, conversas, mensagens, chave, webhook, pedido de chamado e fontes com documentos e trechos pelo superusuário, e confere o `upgrade` (produtos com os mesmos ids, nomes com `:<nível>` renomeados, níveis do workspace pelo assistente mais usado, níveis mínimos do índice), o `downgrade` limpo e cada recusa do `downgrade`. `test_migration_0019.py` faz o mesmo a partir da `0018`: colunas transitórias de `products` removidas, o `downgrade` com o modelo do nível `product_dev` e recusado quando esse nível não tem modelo. `test_migration_0020.py` faz o mesmo a partir da `0019`: tabelas do widget com RLS forçada, colunas e `CHECK`s da conversa do widget, o feedback do visitante, o `downgrade` limpo (com o nome antigo do `CHECK` de canal) e recusado com widget ou feedback sem usuário. `test_migration_0022.py` sobe da `0021` com um produto gravado, confere `products.rerank` `NOT NULL DEFAULT true` (o produto existente fica ligado) e o `downgrade` sem a coluna; `test_migration_0021.py` faz o mesmo a partir da `0020`: `CHECK`s com `mcp`, `ticket_requests.user_id` opcional, conversa `mcp` sem chave recusada, o `downgrade` limpo e recusado com conversa ou mensagem `mcp` ou pedido sem usuário. Os testes que inspecionam `assistants` (das migrações `0008` a `0017`) sobem até `0017`, a última revisão com essa tabela.
**Não entra aqui**: testes de consultas e repositórios de domínio (ficam na pasta do módulo), testes de `core/db.py` (`tests/core/test_db.py`).

**Convenções locais**:
- Cada migração nova estende estes testes (a `0011`, por exemplo, em `test_migration_upgrade_downgrade_run_items`): depois do `upgrade` o objeto existe (com RLS, se for tabela de dados) e depois do `downgrade` não existe mais.
- O teste sempre deixa o banco em `base` ao terminar: o container é compartilhado pela sessão de testes.
- Use `config.attributes["configure_logger"] = False` para o `env.py` não reconfigurar o logging dos testes, e `config.attributes["database_url"]` para apontar para o container.
- Testes que tocam o banco levam `@pytest.mark.integration` (exigem Docker).

**Como testar**: de `backend/`, `uv run pytest tests/migrations`.

**Leia também**: [migrations/AGENTS.md](../../migrations/AGENTS.md); [tests/AGENTS.md](../AGENTS.md).
