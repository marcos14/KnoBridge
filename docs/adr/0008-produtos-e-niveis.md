# ADR 0008 — Produtos e níveis de resposta

> Status: aceito · 2026-10-13 · plano 0009 (F1.1)

## Contexto

Até o plano 0008, quem conversa com o KnoBridge escolhe um **assistente**: prompt, coleções e modelo de LLM ([visão](../01-visao-do-projeto.md), seção 7.5). Toda pergunta busca em todas as fontes das coleções do assistente, e a mesma resposta serve a quem usa o sistema, ao suporte e ao desenvolvimento. Isso tem dois problemas:

1. **Quem pergunta pensa no produto que usa**, não num assistente. Uma empresa com um ERP acaba criando "ERP para clientes", "ERP para suporte" e "ERP para devs", com as mesmas coleções e prompts quase iguais.
2. **O usuário final recebe o que não deveria.** Com o código no índice, uma pergunta de fluxo pode trazer um trecho de código, um commit ou um chamado interno como fonte, e o prompt pedir "não mostre código" não garante nada: o modelo recebeu o trecho.

O [plano 0009](../planos/0009-produtos-e-niveis.md) registra as escolhas do usuário: produto como entidade (D1), três níveis de resposta (D2), nível máximo por pessoa e produto (D3), fontes com nível mínimo filtrado na busca (D4), cards por push (D5), modelo por nível no workspace (D6), chaves com nível máximo e canal público só para usuário final (D8) e os assistentes migrados para produtos (D9). Faltava decidir onde o nível das fontes é aplicado e em que granularidade (D13). O contrato está em [produtos-e-niveis.md](../specs/produtos-e-niveis.md).

## Decisão

1. **Produto substitui assistente** (D1, D9). Produto é uma entidade do workspace com nome, coleções, texto próprio de instruções, idioma, tom, mensagem de "sem fonte", similaridade mínima e o webhook de abrir chamado. Os assistentes viram produtos com o **mesmo id**, e conversas, chaves de API e pedidos de chamado passam a apontar para o produto. As rotas de assistentes do painel saem; a API pública aceita o `assistant_id` antigo como sinônimo, e o `model` antigo continua valendo.
2. **Três níveis de resposta, em ordem** (D2): `end_user` (usuário final: como usar, passo a passo, fluxo; nunca código nem SQL), `support` (suporte: mais exemplos curtos de código, validações e SQL só de leitura, a partir das fontes) e `product_dev` (desenvolvimento e produto: mais planejamento de features e verificação de cards já tratados). O nível de uma pergunta decide as fontes, as instruções e o modelo.
3. **Modelo e instruções por nível, no workspace** (D6, D10). Cada workspace tem uma configuração por nível: credencial, modelo, temperatura e o texto de instruções, com um texto padrão do KnoBridge editável. Os produtos herdam e acrescentam o próprio texto. As regras fixas de citação continuam por último e não se editam.
4. **Nível máximo por pessoa e produto; responde-se no máximo ou abaixo** (D3, D11). O padrão vem do papel (owner e admin: `product_dev`; editor e leitor: `end_user`) e um valor gravado pelo admin sobrepõe. O nível é da conversa e é conferido de novo a cada pergunta.
5. **O nível restringe as fontes no banco** (D4, D13). Cada trecho do índice tem um nível mínimo, o maior entre o da fonte (padrão por tipo, alterável pelo admin), o do documento e o do trecho (refinamentos automáticos dos conectores). A busca híbrida filtra `chunks.min_level` **no SQL dos dois braços**, antes da fusão: um trecho acima do nível da pergunta nunca vira candidato, citação nem contexto do LLM. Padrões: pastas de documentos e conhecimento revisado do harness, `end_user`; chamados e conhecimento inferido, `support`; repositórios Git e cards, `product_dev`. Código detectado numa pasta e a seção de evidências de um item de conhecimento sobem para o nível de quem pode ver código.
6. **Na API, a chave define produtos e nível máximo** (D8, D12). A requisição informa o produto e o nível desejado (até o máximo; sem nível, o máximo da chave). Na API compatível com OpenAI, `model` é `<produto>` ou `<produto>:<nível>`. Um canal público (sem login de quem pergunta, como o futuro widget) só responde no nível `end_user`, por uma regra do núcleo que vale para qualquer canal.
7. **Conversas e mensagens gravam produto e nível**, e o uso e o custo agrupam por eles (D13).

## Alternativas consideradas

- **Produto = assistente, ou produto = coleção** (D1): renomear o assistente não resolve a duplicação por público; amarrar o produto a uma coleção impede um produto com código, documentos e chamados em coleções diferentes (cada coleção fixa um modelo de embedding). Descartadas.
- **Nível só no estilo da resposta, pelo prompt** (D4): barato, mas o modelo recebe o trecho de código e pode citá-lo. "Não mostre" não é controle de acesso. Descartada.
- **Filtrar as fontes depois da busca** (D13): mais simples de escrever, mas os trechos proibidos ocupam as vagas do top-k (a resposta piora para quem tem nível baixo) e um erro de código entre a busca e o filtro vaza o trecho. Filtrar no SQL dá as duas coisas: o melhor top-k permitido e a garantia no banco.
- **Nível só por fonte** (D13): a fonte do runner mistura conhecimento revisado (para o usuário final) e inferido (para o suporte), e uma pasta pode ter código. Sem refinamento por documento e trecho, ou o usuário final perde o revisado, ou recebe o inferido e o código.
- **Um nível por pessoa para todos os produtos, ou nível pelo papel** (D3): o acesso varia por produto (o analista de suporte do ERP é usuário final do portal), e o papel do workspace diz o que a pessoa administra, não o que ela pode ler.
- **Modelo por produto e nível** (D6): nove combinações para três produtos, para pouco ganho. O modelo mais capaz vai para o nível que precisa, uma vez.
- **Nível fixo por chave** (D8): obrigaria uma chave por nível na mesma integração. Com o máximo na chave e o nível na requisição, uma chave serve ao suporte e ao usuário final do mesmo sistema.
- **Manter as rotas de assistentes como apelido**: o assistente tinha modelo próprio, que não existe mais no produto; o apelido mentiria nos campos. Só o painel as usava, e ele muda junto.

## Consequências

- Tabelas novas `products`, `product_collections`, `workspace_levels` e `member_product_levels`; `min_level` em `sources`, `documents` e `chunks`; produto e nível em `conversations` e `messages`; `product_ids` e `max_level` em `api_keys`. Migração `0018` com os dados dos assistentes ([modelo-de-dados.md](../specs/modelo-de-dados.md)).
- Conversas e chaves existentes ficam com `product_dev`, o nível que equivale ao que elas viam (todas as fontes). Integrações em uso continuam recebendo as mesmas fontes; o admin baixa o máximo de cada chave quando quiser.
- Os três níveis de um workspace herdam o modelo do assistente mais usado. Produtos que vieram de assistentes com outro modelo passam a responder com o do nível; a tela de níveis mostra o custo estimado de cada um para o admin ajustar.
- Mudar o nível mínimo de uma fonte vale na hora, recalculando `chunks.min_level` sem reindexar (fontes de chamados e cards já não têm o bruto). Só owner e admin mudam, com auditoria.
- A rota "testar busca" das coleções passa a exigir editor e recebe o nível, para não virar um atalho de leitura de código por quem tem nível `end_user`.
- Este ADR substitui o item 4 do [ADR 0007](0007-chaves-e-api-publica.md) (escopo da chave por assistente, agora por produto e com nível máximo) e a parte "um modelo por assistente" da API compatível com OpenAI, e o item 6 do [ADR 0006](0006-chamados-por-push.md) (webhook por assistente, agora por produto).
- O texto padrão das instruções vive no código e melhora com as versões; o workspace que editou o texto fica com o seu.
