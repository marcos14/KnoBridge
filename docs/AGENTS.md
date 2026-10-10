# docs/

**Função**: toda a documentação e todos os planos do KnoBridge. Se é texto para humanos ou agentes lerem e não é código, fica aqui.

**Entra aqui**
- `01-visao-do-projeto.md`: fonte da verdade sobre produto, arquitetura, stack, decisões (seção 9) e roadmap. Documentos numerados `NN-nome-em-kebab.md` por ordem de leitura.
- `planos/NNNN-slug.md`: um plano por pedido do usuário (fluxo da seção 3 do `AGENTS.md` da raiz), com andamento, decisões e pendências no frontmatter. Modelo em `planos/0000-modelo.md`; convenções em `planos/AGENTS.md`.
- `adr/NNNN-titulo-curto.md`: decisões de arquitetura (contexto, decisão, alternativas, consequências, status). Numeração sequencial com 4 dígitos.
- `specs/`: contratos. OpenAPI, modelo de dados, formato do `.md` de conhecimento e seu frontmatter, protocolo dos conectores, schema JSON do harness, formato do grafo do canvas.
- `guias/`: como operar. Subir o ambiente, conectar Slack ou Google Chat, rodar o harness, criar um conector.
- `pesquisa/`: comparativos e notas de investigação, com data e links.
- `eval/` (só na fase 3): conjuntos de perguntas e respostas esperadas, sintéticos.

**Não entra aqui**
- Código, scripts ou notebooks executáveis (vão para `backend/`, `frontend/`, `scripts/`).
- Segredos, dados de clientes, exportações de chamados reais, trechos de código de sistemas de terceiros.
- Artefatos gerados (relatórios de cobertura, builds, logs de execução).

**Convenções**
- Markdown, pt-BR, frases curtas. Diagramas em Mermaid dentro do próprio `.md`. Links relativos entre documentos.
- Cabeçalho dos documentos vivos: `> Rascunho vX.Y · AAAA-MM-DD · Status`, seguido de uma linha "Mudanças da vX.Y" quando houver revisão. Bump de versão a cada revisão que muda decisão ou escopo.
- Tabelas para comparar; listas para passos; parágrafos curtos para argumentar. Toda afirmação sobre ferramenta externa tem link na seção "Referências" do documento.
- Datas sempre absolutas (`2026-10-10`), nunca "semana que vem".
- Decisão nova ou revertida: ADR primeiro, depois uma linha na tabela da seção 9 da visão apontando para o ADR.
- Perguntas em aberto ficam na seção 13 da visão até serem respondidas. A resposta vira ADR ou texto na seção certa, e a pergunta sai da lista.
- Subpastas novas aqui também recebem `AGENTS.md`.

**Como testar**: não há testes automatizados de docs por ora. Antes de entregar, confira que links relativos resolvem, que cada tabela tem o mesmo número de colunas em todas as linhas e que o Mermaid renderiza na pré-visualização do editor.

**Leia também**: [AGENTS.md da raiz](../AGENTS.md), seção 7.
