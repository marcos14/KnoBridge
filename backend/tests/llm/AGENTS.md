# backend/tests/llm/

**Função**: testes de `src/knobridge/llm/`: isolamento por RLS de `provider_credentials` e a cifra da chave amarrada à linha.

**Entra aqui**: `test_provider_credentials.py` (RLS como dono e não dono pela fixture `rls_database_url`, inserção em workspace alheio, chave gravada cifrada e revelada, texto cifrado movido para outra linha recusado). As regras de negócio pela API (papéis, máscara, nome repetido, `fake` em produção) ficam em `tests/api/test_providers.py`; a primitiva de cifra, em `tests/core/test_crypto.py`.
**Não entra aqui**: testes de rotas (`tests/api/`), da cadeia de migrações (`tests/migrations/`), chamadas a provedores reais.

**Convenções locais**:
- Testes com banco levam `@pytest.mark.integration`; o banco é compartilhado, então cada teste cria seus workspaces e usuários com slugs e e-mails únicos.
- Chaves de API só sintéticas (ex.: `sk-test-...`); segredo raiz de teste fixo no próprio arquivo.
- Relógio `FrozenClock`; sem rede.

**Como testar**: de `backend/`, `uv run pytest tests/llm` (exige Docker).

**Leia também**: [llm/AGENTS.md](../../src/knobridge/llm/AGENTS.md); [tests/AGENTS.md](../AGENTS.md).
