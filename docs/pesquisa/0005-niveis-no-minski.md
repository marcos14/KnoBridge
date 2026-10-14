# Níveis de resposta no Minski

> 2026-10-13 · Plano [0009](../planos/0009-produtos-e-niveis.md), subfase F4.2 · executado pelo orquestrador na stack local do [ensaio 0002](0002-ensaio-harness-minski.md), fora da CI

Mesmo índice do Minski dos ensaios [0001](0001-ensaio-minski.md) e [0002](0002-ensaio-harness-minski.md), agora com o código do plano 0009: o assistente virou o produto MAESTRO, e cada pergunta foi feita nos três níveis de resposta (Usuário final, Suporte, Desenvolvimento e produto). Como nos ensaios anteriores, este registro traz métricas, perguntas e conclusões, sem trechos do conteúdo indexado nem das respostas (regra 9).

## Configuração

| Item | Valor |
|---|---|
| Stack | `knobridge-minski` dos ensaios anteriores, atualizada para este código; as migrações `0014` a `0019` rodaram sobre os dados reais sem erro |
| Produto | MAESTRO (o assistente "Minski Luna" migrado, mesmo id e mesma coleção), similaridade mínima 0,35 |
| Fontes e nível mínimo | dois repositórios Git (2.106 e 312 documentos, `product_dev`, padrão do tipo), pasta de documentos soltos (15 documentos, `end_user`) e duas fontes de runner com o conhecimento do harness (36 e 16 itens, `end_user`; todos os itens são inferidos, então os documentos ficaram em `support`) |
| Trechos por nível efetivo | 593 `end_user`, 163 `support`, 19.729 `product_dev` |
| Modelos | Usuário final `openai/gpt-4.1-mini`; Suporte `anthropic/claude-sonnet-5.5`; Desenvolvimento e produto `anthropic/claude-opus-5.5`; todos pelo OpenRouter, temperatura 0,2 e instruções padrão do nível |
| Perguntas | as 11 dos ensaios 0001 e 0002 e 6 novas (abaixo), cada uma numa conversa nova em cada nível: 51 respostas |

Perguntas novas:

| # | Tipo | Pergunta |
|---|---|---|
| 12 | suporte: SQL | Monte uma consulta SQL para listar os Work Items que passaram do teto de gasto com IA, com o gasto e o teto de cada um. |
| 13 | suporte: validação | Que validações o sistema faz antes de aceitar a inscrição de um Runtime numa organização? Mostre um exemplo de pedido recusado. |
| 14 | suporte: SQL | Como consultar no banco quais usuários tiveram o papel rebaixado e quando isso aconteceu? |
| 15 | dev: planejar | Quero que o Owner defina também um teto de gasto por projeto, além do teto por Work Item. Como planejar essa feature e o que já existe para reaproveitar? |
| 16 | dev: já tratado? | O pedido de acompanhar o Runtime em tempo real (`observe --watch`) já foi atendido em alguma entrega? Em qual versão ou commit? |
| 17 | dev: já tratado? | Já foi feito algo para avisar o usuário quando o papel dele muda? Em qual entrega e o que ficou de fora? |

## O filtro de nível

Nenhum vazamento: o que cada nível citou nas 17 perguntas.

| Nível | Citações por tipo |
|---|---|
| Usuário final | 124 Markdown, 36 PDF (só documentos soltos) |
| Suporte | 64 itens de conhecimento, 66 Markdown, 30 PDF |
| Desenvolvimento e produto | 37 itens de conhecimento, 73 Markdown, 11 commits, 17 `.ts`, 2 `.tsx`, 4 `.go`, 7 `.json` e outros arquivos do repositório |

Código, commits e arquivos do repositório só apareceram em Desenvolvimento e produto; o conhecimento do harness (inferido) só a partir de Suporte. A pergunta sem relação (feijoada) ficou sem fonte nos três níveis, sem chamar o LLM.

## Qualidade lida pelo orquestrador

Cada resposta foi lida e classificada como útil e correta para o público do nível, falha (resposta errada, imprecisa ou que fere as instruções do nível) ou "não sei". A pergunta 11 (sem fonte nos três) fica fora da contagem.

| Nível | Útil e correta | Falha | "Não sei" |
|---|---|---|---|
| Usuário final | 7 (1, 2, 3, 4, 5, 6, 10) | 6 (8, 9, 13, 15, 16, 17) | 3 (7, 12, 14) |
| Suporte | 12 (1 a 6, 8, 9, 10, 14, 15, 17) | 0 | 4 (7, 12, 13, 16) |
| Desenvolvimento e produto | 14 (1 a 10, 13, 14, 15, 16) | 0 | 2 (12, 17) |

- **Desenvolvimento e produto** respondeu as perguntas de código com caminho, função e trecho, a do `observe --watch` com o commit e o card ligado a ele, e planejou o teto por projeto separando o que as fontes confirmam do que é proposta. É o único nível que respondeu a pergunta 7, cuja resposta está num commit.
- **Suporte** usou o conhecimento do harness e os excertos das evidências para explicar onde a regra fica e mostrar poucas linhas de código. Recusou planejar (pergunta 15) e explicou o que existe hoje, como as instruções pedem. Na pergunta 17 distinguiu bem o que foi planejado do que foi entregue.
- **Usuário final** respondeu bem as perguntas de regra de negócio e de fluxo, a uma fração do custo. As seis falhas têm a mesma origem: a pasta de documentos soltos do Minski mistura o manual do produto com PRD, planos e logs de execução, e o `gpt-4.1-mini` repetiu o que encontrou ali (nome de arquivo, commit, nome de teste), planejou a feature da pergunta 15 e apresentou como entregue um item que só estava planejado (pergunta 17).

## Achados e correções

1. **O texto padrão do Usuário final não proibia planejar.** O do Suporte proíbe e o Sonnet obedeceu; o do Usuário final não dizia nada, e o modelo planejou. Correção: a linha "Planejar funcionalidades novas ou mudanças no produto" entrou nas proibições do Usuário final, na spec e em `levels/defaults.py`, com um teste novo (`tests/levels/test_defaults.py`) que compara os três textos padrão, palavra por palavra, com a spec (o teste antigo só olhava o começo e o fim). Repetidas no Usuário final, as perguntas 8, 9 e 15 continuaram com as mesmas falhas com o `gpt-4.1-mini`: com um contexto cheio de documentos internos, o modelo pequeno não segura a regra.
2. **Modelo do Usuário final.** Com o `anthropic/claude-haiku-4.5` (US$ 0,006 por resposta, 3 vezes o `gpt-4.1-mini`), as perguntas 8, 9 e 15 passaram a respeitar as proibições, mas a pergunta 1, de regra de negócio, virou "não sei". Nenhum dos dois resolve sozinho: o que resolve é a fonte (achado 3).
3. **O nível mínimo é por fonte, então a pasta precisa ser separada por público.** Com o manual do produto e os documentos internos na mesma pasta, o Usuário final recebe os dois. Recomendação no guia [produtos-e-niveis.md](../guias/produtos-e-niveis.md): manuais e ajuda numa fonte `end_user`, documentos internos (PRD, planos, decisões, logs) numa fonte `support` ou `product_dev`.
4. **Conhecimento do harness não revisado não chega ao Usuário final.** Todos os itens do Minski são inferidos, que por regra ficam em Suporte. Revisar no painel os itens que explicam regras de negócio libera esses itens para o Usuário final, que hoje só tem os documentos soltos.
5. **Consultas SQL dependem de o esquema entrar no contexto.** Nas perguntas 12 e 14, os 10 trechos do contexto foram todos sobre o assunto (teto de gasto, papéis), nenhum do esquema do banco, que está indexado (`schema.prisma` em 85 trechos e as migrações) mas na fonte Git, em `product_dev`. Repetida em Desenvolvimento e produto citando os nomes das tabelas, a pergunta 12 trouxe o esquema e uma consulta parcial e segura, dizendo o que faltava. Para o Suporte montar SQL, o esquema precisa estar numa fonte de nível `support` (por exemplo, uma pasta com o esquema e as migrações) e a busca precisa achar as tabelas a partir de uma pergunta em linguagem de negócio; fica como candidato a próximo passo (busca em duas etapas ou mais contexto para perguntas de SQL), sem mudança neste plano.
6. **"Não sei" com fontes no contexto.** Em 9 das 48 respostas com fontes, o modelo respondeu "não sei" mesmo com 10 trechos, e em várias outro nível respondeu bem com fontes parecidas (13, 16 e 17). É o lado conservador da regra das citações: não se trata de um defeito do filtro. O efeito aparece mais no Haiku e no Sonnet.

## Custo e tempo

| Nível | Respostas | Tokens de entrada (média) | Tokens de saída (média) | Custo por resposta | Tempo (mediana) |
|---|---|---|---|---|---|
| Usuário final | 16 | 4.586 | 222 | US$ 0,0022 | 3,2 s |
| Suporte | 16 | 5.961 | 959 | US$ 0,0215 | 9,3 s |
| Desenvolvimento e produto | 16 | 7.048 | 1.454 | US$ 0,0573 | 16,0 s |

O nível mais capaz custa 26 vezes o Usuário final por resposta, com mais contexto (código e commits entram nos trechos) e respostas mais longas. As 51 respostas custaram US$ 1,30; com as repetições dos achados, US$ 1,39 no ensaio inteiro. A reindexação não foi necessária: os trechos já indexados ganharam o nível pela migração.

## Como repetir

```bash
# stack do Minski com o código atual (portas próprias; a pasta de fontes aponta para os repositórios)
KNOBRIDGE_SOURCES_DIR=<pasta com os repositórios> API_PORT=28000 ... docker compose -p knobridge-minski up -d --build --wait
# painel: Configurações > Níveis de resposta (um modelo por nível) > Produtos (ligar a coleção) > Chat (escolher produto e nível)
# ou pela API: POST /v1/workspaces/{id}/conversations {"product_id", "level"} e POST .../messages, uma conversa por pergunta e nível
```
