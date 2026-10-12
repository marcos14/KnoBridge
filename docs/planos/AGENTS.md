# docs/planos/

**Função**: um arquivo por pedido do usuário, com o plano aprovado, o andamento (no frontmatter), as decisões tomadas e as pendências que dependem do usuário. É a memória de execução do projeto: quem chega depois lê o frontmatter e sabe onde cada pedido está, e lê o corpo e sabe o que foi combinado.

**Entra aqui**: `NNNN-slug.md` (NNNN sequencial a partir de 0001, slug em kebab-case, pt-BR), sempre criados a partir de [0000-modelo.md](0000-modelo.md). Nada mais.
**Não entra aqui**: ADRs (`docs/adr/`), specs (`docs/specs/`), notas de pesquisa (`docs/pesquisa/`), código.

**Convenções**
- O frontmatter é a fonte do andamento. O corpo é o contrato (pedido original, entendimento, critérios de aceite, fases e subfases) e o registro de andamento.
- Status do plano: `rascunho`, `aguardando_aprovacao`, `aprovado`, `em_execucao`, `bloqueado`, `concluido`, `cancelado`. Status de fase e subfase: `pendente`, `em_execucao`, `concluida`, `bloqueada`, `cancelada`.
- Um plano só sai de `aguardando_aprovacao` com resposta afirmativa explícita do usuário, registrada em `aprovado_em` e `aprovado_por`. Sem isso, nenhuma subfase começa.
- Atualize o frontmatter a cada transição de estado (início e fim de subfase, bloqueio, aprovação, encerramento), nunca só no fim.
- Nunca apague fases ou subfases canceladas: marque `status: cancelada` e explique no registro de andamento.
- Numeração: o próximo número é o maior existente + 1; nunca reutilize. O `0000-modelo.md` nunca é executado.
- Commits de subfase trazem `[plano NNNN Fx.y]` na primeira linha; `git log --grep "plano NNNN"` lista tudo de um plano. O hash entra em `commit` da subfase na atualização seguinte.
- Toda decisão (do agente ou do usuário) vai para `decisoes[]`; toda pergunta aberta ao usuário vai para `pendencias_usuario[]` com a resposta quando vier. Decisão de arquitetura também ganha ADR.
- Datas sempre absolutas (`AAAA-MM-DD`).

**Como testar**: o frontmatter precisa ser YAML válido (um parser YAML deve ler sem erro) e seguir os campos do modelo. Quando `scripts/check_plans.py` existir (bootstrap), a CI valida o schema e os status.

**Leia também**: seção 3 do [AGENTS.md da raiz](../../AGENTS.md); [0000-modelo.md](0000-modelo.md).
