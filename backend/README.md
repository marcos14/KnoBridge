# KnoBridge — backend

API e serviços Python do KnoBridge. Visão geral e regras em [`AGENTS.md`](AGENTS.md) e na [documentação](../docs/).

## Instalar

Requer [uv](https://docs.astral.sh/uv/) (ele instala o Python 3.12 sozinho). No Windows, exporte `PYTHONUTF8=1`.

```sh
cd backend
uv sync
cp .env.example .env   # opcional; ajuste as variáveis KNOBRIDGE_*
```

## Rodar a API localmente

```sh
uv run knobridge-api
# ou, com reload:
uv run uvicorn knobridge.api.app:create_app --factory --reload
```

Teste rápido: `curl http://127.0.0.1:8000/v1/health/live`. OpenAPI em `http://127.0.0.1:8000/docs`.

## Testar

```sh
uv run ruff check . && uv run ruff format --check . && uv run pyright
uv run pytest   # inclui cobertura de linhas e branches com gate de 95%
```
