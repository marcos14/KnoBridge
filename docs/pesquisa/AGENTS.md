# docs/pesquisa/

**Função**: notas de investigação, ensaios e comparativos que embasam decisões do KnoBridge, cada uma com data, contexto e números.

**Entra aqui**: `NNNN-titulo-curto.md` (4 dígitos, sequencial, kebab-case pt-BR): ensaios com dados reais ou sintéticos, comparações de modelos e bibliotecas, medições de custo e qualidade.

**Não entra aqui**: decisões (viram ADR em [`../adr/`](../adr/AGENTS.md)), contratos ([`../specs/`](../specs/AGENTS.md)), guias de operação ([`../guias/`](../guias/AGENTS.md)) e planos ([`../planos/`](../planos/)).

**Convenções locais**:
- Cabeçalho com data, plano/subfase de origem e onde rodou.
- Regra 9 do [`AGENTS.md`](../../AGENTS.md) raiz: nada de conteúdo real de clientes ou de projetos de terceiros. Ensaios com dados reais registram métricas, perguntas e conclusões, sem trechos do conteúdo indexado nem das respostas.
- Termine com "Como repetir" quando o ensaio for reproduzível.

**Como testar**: `cd scripts && uv run python check_agents_md.py` e a checagem de links relativos do pre-commit.

**Leia também**: [`../AGENTS.md`](../AGENTS.md).
