# MCP e widget no Minski

> 2026-10-14 · Plano [0010](../planos/0010-canais-mcp-e-widget.md), subfase F5.2 · executado pelo orquestrador na stack local do [ensaio 0005](0005-niveis-no-minski.md), fora da CI

O mesmo índice do Minski dos ensaios anteriores, agora consultado pelos dois canais novos:
- **MCP:** o Claude Code ligado ao servidor MCP do KnoBridge com uma chave Desenvolvimento e produto.
- **Widget:** a API pública do widget no nível Usuário final.

Como nos ensaios anteriores, este registro traz métricas, perguntas e conclusões, sem trechos do conteúdo indexado nem das respostas (regra 9).

## Configuração

| Item | Valor |
|---|---|
| Stack | `knobridge-minski`, atualizada para este código; as migrações `0020` e `0021` rodaram sobre os dados reais sem erro |
| Produto | MAESTRO (o mesmo do ensaio 0005), com os mesmos níveis: Usuário final `openai/gpt-4.1-mini`, Desenvolvimento e produto `anthropic/claude-opus-5.5` |
| Cliente MCP | Claude Code 2.1.299 em modo não interativo (`claude -p`), modelo Sonnet, só o servidor `knobridge` (`--strict-mcp-config`) e nenhuma ferramenta local |
| Chave | `kbk_` com o produto MAESTRO e nível máximo Desenvolvimento e produto |
| Modos comparados | **search**: o Claude Code só pode usar `list_products`, `search_knowledge` e `get_document`, e o modelo do IDE escreve a resposta. **ask**: só `list_products` e `ask`, e o Claude Code repassa a resposta do KnoBridge. |
| Widget | um widget do MAESTRO com uma origem permitida, chamado pela API pública com o header `Origin`, como o navegador faz |

Perguntas do MCP (todas no nível Desenvolvimento e produto), tiradas dos ensaios 0001, 0002 e 0005:

| # | Tipo | Pergunta |
|---|---|---|
| 1 | como funciona | Como funciona o teto de gasto com IA por Work Item? |
| 2 | onde no código | Em que arquivo fica a tabela de preços embutida dos modelos de LLM? |
| 3 | onde no código | Onde no código do Runtime é tratado o comando `answers --wait`? |
| 4 | quando | O que mudou no Runtime na versão V3 em relação ao `observe --watch`? |
| 5 | suporte: SQL | Monte uma consulta SQL para listar os Work Items que passaram do teto de gasto com IA, com o gasto e o teto de cada um. |
| 6 | suporte: validação | Que validações o sistema faz antes de aceitar a inscrição de um Runtime numa organização? Mostre um exemplo de pedido recusado. |
| 7 | dev: planejar | Quero que o Owner defina também um teto de gasto por projeto, além do teto por Work Item. Como planejar essa feature e o que já existe para reaproveitar? |
| 8 | dev: já tratado? | O pedido de acompanhar o Runtime em tempo real (`observe --watch`) já foi atendido em alguma entrega? Em qual versão ou commit? |
| 9 | dev: já tratado? | Já foi feito algo para avisar o usuário quando o papel dele muda? Em qual entrega e o que ficou de fora? |

No widget foram feitas seis perguntas do ensaio 0005 no nível Usuário final: 1, 2, 5, 8, 10 e 15 da numeração daquele relatório.

## MCP: `search_knowledge` x `ask`

| Modo | Respostas úteis e corretas | Chamadas ao KnoBridge | Custo do Claude Code | Custo do KnoBridge | Total por pergunta | Tempo (mediana) |
|---|---|---|---|---|---|---|
| search | **9 de 9** | 20 (1 a 4 buscas por pergunta, 1 `get_document`) | US$ 0,164 por pergunta | só o embedding da consulta | cerca de US$ 0,16 | 19 s |
| ask | 7 de 9 ("não sei" nas perguntas 5 e 9) | 9 | US$ 0,077 por pergunta | US$ 0,053 por resposta (Opus) | cerca de US$ 0,13 | 27 s |

- **Nas perguntas fáceis os modos empatam.** Nas perguntas 1 a 4 e 6 a 8, os dois acertaram com as mesmas fontes: arquivo e linhas, o commit e o card ligado a ele, a tabela de recusas da inscrição. O `ask` traz o mesmo texto do chat do painel.
- **Nas difíceis, buscar várias vezes vence.** Na pergunta 5 (SQL), que nenhum nível respondeu no ensaio 0005, o Claude Code fez quatro buscas e encontrou as tabelas e colunas nas migrações. Montou a consulta e disse que uma das colunas era inferida. Na pergunta 9, três buscas acharam o commit da entrega e separaram o que foi feito do que não foi; o `ask` disse "não sei" com dez trechos sem relação. A busca única do `ask` fica presa à primeira formulação; o cliente reformula a pergunta e busca de novo.
- **Custo e tempo:** o modo search custa um pouco mais por pergunta (US$ 0,16 contra US$ 0,13), porque o Claude Code lê mais trechos. Mas a cobrança cai na conta do cliente MCP, não na do KnoBridge, e a resposta sai mais rápido (19 s contra 27 s, porque o `ask` espera a resposta inteira do Opus antes de devolver).
- **Nível:** nenhum pedido acima do máximo da chave foi necessário. A recusa (`level_not_allowed`) está coberta pelo E2E da F5.1.
- **ToolSearch:** em cada execução, o Claude Code chamou primeiro o `ToolSearch`, a ferramenta dele que carrega as definições das ferramentas MCP sob demanda. Não é chamada ao KnoBridge.

## Widget no nível Usuário final

| Verificação | Resultado |
|---|---|
| Conversa pedindo nível Suporte | 403 `level_not_allowed` |
| `config` com uma origem fora da lista | 403 `widget_origin_not_allowed` |
| Fontes citadas nas 6 respostas | só Markdown e PDF da pasta de documentos (nenhum código, commit nem conhecimento inferido) |
| Evento `done` para o visitante | sem modelo, tokens nem custo |
| Custo gravado | US$ 0,0137 nas 6 respostas (US$ 0,0023 por resposta) |
| Tempo | 2,5 a 7,4 s por resposta |

As respostas são as mesmas que o chat do painel dá no nível Usuário final, com as mesmas falhas do [ensaio 0005](0005-niveis-no-minski.md#qualidade-lida-pelo-orquestrador). O `gpt-4.1-mini` diz o nome de um arquivo interno (pergunta 8), planeja a feature pedida (pergunta 15, mesmo com a instrução nova que proíbe planejar) e chama de "mensal" o teto do item, que vale pela vida inteira (pergunta 1). Como no 0005, a causa é a pasta de documentos misturar o manual do produto com documentos internos; a recomendação continua a do guia [produtos-e-niveis.md](../guias/produtos-e-niveis.md).

## Conclusões

1. **Os dois canais respeitaram o contrato com dados reais:**
   - o widget nunca saiu do nível Usuário final;
   - o MCP respondeu no nível da chave;
   - o uso apareceu no canal certo (`mcp` e `widget`);
   - as migrações novas rodaram sobre o índice do Minski sem erro.
2. **Para a equipe de desenvolvimento, recomende `search_knowledge`.** Ele acertou tudo, inclusive a consulta SQL e o "já foi tratado?" que a busca única não resolve, sem custo de LLM no KnoBridge. O guia [conectar-pelo-mcp.md](../guias/conectar-pelo-mcp.md) e as instruções do servidor já orientam o modelo nessa direção.
3. **A busca em várias etapas resolve a lacuna do 0005.** O cliente MCP buscar várias vezes resolveu o que o ensaio 0005 deixou como próximo passo (SQL do Suporte e perguntas difíceis). Fica a sugestão de dar ao `ask` e ao chat do painel uma busca em mais de uma etapa (reformular e buscar de novo antes de dizer "não sei"). Sem mudança neste plano.
4. **Nenhum defeito novo apareceu no ensaio.** O defeito do canal MCP (erros de ferramenta virando erro de protocolo no cliente oficial em TypeScript) foi achado e corrigido no E2E da F5.1.

## Custo

| Parte | Custo |
|---|---|
| Claude Code (Sonnet), 18 execuções mais 2 de teste | US$ 2,33 |
| KnoBridge, 10 respostas de `ask` (Opus) | US$ 0,53 |
| KnoBridge, 6 respostas do widget (`gpt-4.1-mini`) | US$ 0,01 |
| **Total** | **cerca de US$ 2,87** |

## Como repetir

```bash
# stack do Minski com o código atual (portas próprias; a pasta de fontes aponta para os repositórios)
KNOBRIDGE_SOURCES_DIR=<pasta com os repositórios> API_PORT=28000 ... docker compose -p knobridge-minski up -d --build --wait
# painel: Chaves de API > nova chave com o produto e o nível > "Conectar por MCP" (comandos do Claude Code, do Cursor e do Codex)
claude mcp add --transport http knobridge http://localhost:28000/v1/mcp --header "Authorization: Bearer $KNOBRIDGE_API_KEY"
# widget: Widgets > novo widget com a origem da página de teste > trecho de instalação
```
