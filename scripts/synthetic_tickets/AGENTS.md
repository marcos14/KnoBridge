# scripts/synthetic_tickets/

**Função**: gerador determinístico de dados sintéticos para chamados (plano 0005): chamados em pt-BR de um ERP fictício (Vértice ERP), no formato de [chamados.md](../../docs/specs/chamados.md), com dados pessoais semeados e registrados num gabarito para medir a anonimização, e artigos de ajuda com perguntas para comparar modelos de embedding. Nada aqui é dado real (regra 9).

**Entra aqui**:
- `problem.py`: o `Problem` (títulos, queixas, sintoma, causa, passos, solução, duas perguntas).
- `catalog_loja.py` (Caixa, Fiscal, Estoque) e `catalog_gestao.py` (Financeiro, Folha, Vendas): 24 problemas recorrentes com solução; `catalog.py` junta tudo e fixa datas, pesos de status e o domínio fictício.
- `people.py`: nomes, empresas e dados pessoais gerados (CPF e CNPJ com dígitos válidos, cartão que passa no Luhn, telefone com DDD, IPv4, e-mail em `.example`, número de versão com cara de IP).
- `answer_key.py`: o gabarito de um chamado (`anonimizar` com o marcador esperado, `preservar`, `nao_detectavel`, cada item com `onde` e `nota_interna`).
- `tickets.py`: um chamado (papéis, notas internas, mensagem de sistema, HTML em parte das respostas, abertos, pendentes, resolvidos e fechados).
- `articles.py`: um artigo Markdown por problema, uma visão geral por produto (distrator) e as perguntas com o artigo e os chamados resolvidos esperados.
- `generate.py` (`generate(seed, count)`, `write`) e `cli.py` (`main(argv)`, recusa pasta de saída dentro do repositório).

**Não entra aqui**: o conjunto gerado (fica fora do repositório; só o exemplo do E2E em `frontend/e2e/stack/fixtures/tickets/`), medições de anonimização ou de embedding (relatório em `docs/pesquisa/`), código do produto.

**Convenções locais**:
- Determinístico: um `random.Random(seed)` passado adiante, datas a partir de `catalog.FIRST_DAY`, sem relógio real. Mudou a ordem de sorteio, muda todo o conjunto: regenere o exemplo do E2E (abaixo).
- Todo dado pessoal escrito num texto passa pelo `AnswerKey` no mesmo momento; o teste confere que cada valor está no campo de `onde`.
- Primeiros nomes com 3 ou mais letras, que não são palavras do português, sem repetir num chamado (um marcador por pessoa).
- Exemplo do E2E: `uv run python -m synthetic_tickets --seed 1 --tickets 4 --out <pasta temporária>` e copie `tickets.jsonl` para `frontend/e2e/stack/fixtures/tickets/chamados.jsonl` (o teste `repo` confere).

**Como testar** (de `scripts/`): `uv run pytest tests/test_synthetic_tickets.py` (o gate de 95% vale para o projeto inteiro: `uv run pytest`).

**Uso**: `uv run python -m synthetic_tickets --seed 7 --tickets 300 --out ../../kb-sinteticos` gera `tickets.jsonl` (um chamado puro por linha, aceito pelo upload e embrulhável em lotes da API), `gabarito.json`, `perguntas.json` e `docs/*.md`.

**Leia também**: [scripts/AGENTS.md](../AGENTS.md); [docs/specs/chamados.md](../../docs/specs/chamados.md) (formato e regras de anonimização); [docs/guias/receber-chamados-por-api.md](../../docs/guias/receber-chamados-por-api.md).
