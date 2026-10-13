# backend/src/knobridge/assistants/

**Função**: transitória (plano 0009). Desde a migração `0018`, os assistentes são produtos ([products/AGENTS.md](../products/AGENTS.md)), e desde a F2.1 o serviço, a listagem, a duplicação e as rotas são os de produtos (`products/`, `api/products.py`). Este pacote só mantém os apelidos que a rodada de chat, a recuperação, os chamados, as chaves e o uso ainda importam; sai quando esses módulos passarem a importar `knobridge.products.models` (F2.2 e F2.4).

**Entra aqui**:
- `models.py`: só reexporta `Product`, `ProductCollection` e `ProductTone` como `Assistant`, `AssistantCollection` e `AssistantTone`, e as constantes de `products/models.py` e de `levels/level.py` (`DEFAULT_NO_SOURCE_MESSAGE`, `DEFAULT_LANGUAGE`, `DEFAULT_MIN_SIMILARITY`, `MIN_SIMILARITY`/`MAX_SIMILARITY`, `DEFAULT_TEMPERATURE`, `MIN_TEMPERATURE`/`MAX_TEMPERATURE`, `TICKET_WEBHOOK_URL_MAX_LENGTH`).

**Não entra aqui**: código novo. Produtos (`products/`), níveis (`levels/`), routers (`api/`), conversas (`conversations/`), migrações (`backend/migrations/`).

**Convenções locais**: não acrescente nada; código novo importa `knobridge.products.models`. Quem ainda importa daqui: `conversations/` (`service.py`, `admin.py`, `prompt.py`), `retrieval/retriever.py`, `tickets/` (`delivery.py`, `requests.py`, `webhook.py`, `webhook_secret.py`), `apikeys/`, `usage/` e `api/openai_compat.py`.

**Como testar**: os testes de produtos ficam em `tests/products/` e `tests/api/test_product*.py`. Gate da suíte inteira, de `backend/`: `uv run pytest`.

**Leia também**: [products/AGENTS.md](../products/AGENTS.md); [levels/AGENTS.md](../levels/AGENTS.md); [docs/specs/produtos-e-niveis.md](../../../../docs/specs/produtos-e-niveis.md).
