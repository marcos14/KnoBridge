# docs/adr/

**Função**: registros de decisão de arquitetura (ADR) do KnoBridge. Cada decisão nova ou revertida que muda stack, modelo de dados, contrato ou algo da seção 9 da [visão](../01-visao-do-projeto.md) ganha um arquivo aqui.

**Entra aqui**: `NNNN-titulo-curto.md` (4 dígitos, sequencial, título em kebab-case pt-BR), um por decisão.
**Não entra aqui**: planos de execução (`docs/planos/`), contratos detalhados (`docs/specs/`), guias (`docs/guias/`), notas de pesquisa (`docs/pesquisa/`).

**Convenções locais**:
- Cabeçalho: `# ADR NNNN — Título` e a linha `> Status: proposto | aceito | substituído por ADR NNNN · AAAA-MM-DD · plano NNNN`.
- Seções, nesta ordem: Contexto, Decisão, Alternativas consideradas, Consequências.
- ADR aceito não é reescrito: mudança de decisão é um ADR novo que marca o antigo como substituído.
- Todo ADR ganha uma referência na tabela da seção 9 da visão, na mesma entrega.

**Como testar**: sem testes automatizados; confira links relativos e a referência na visão.

**Leia também**: [docs/AGENTS.md](../AGENTS.md); seção 7 do [AGENTS.md da raiz](../../AGENTS.md).
