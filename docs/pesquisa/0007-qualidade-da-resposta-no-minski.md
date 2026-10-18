# Qualidade da resposta no Minski

> 2026-10-17 · Plano [0011](../planos/0011-qualidade-da-resposta.md), subfase F4.3 · executado pelo orquestrador na stack local dos ensaios [0005](0005-niveis-no-minski.md) e [0006](0006-mcp-e-widget-no-minski.md) e numa stack isolada para o conjunto sintético, fora da CI

Mesmo índice e mesmas perguntas dos ensaios 0005 (17 perguntas nos três níveis) e 0006 (9 perguntas pelo `ask` do MCP), agora com o código do plano 0011: busca em etapas, reranker self-host e limiar por modelo de embedding. Como nos ensaios anteriores, este registro traz métricas, perguntas e conclusões, sem trechos do conteúdo indexado nem das respostas (regra 9). O conjunto sintético de `scripts/eval/` rodou com LLM real numa stack à parte.

## Configuração

| Item | Valor |
|---|---|
| Stack | `knobridge-minski` dos ensaios anteriores, atualizada para este código; as migrações `0022` a `0025` rodaram sobre os dados reais sem erro |
| Produto | MAESTRO, a mesma coleção; limiar em branco (padrão do modelo, 0,35 para o `openai/text-embedding-3-small`) |
| Modelos | Usuário final `openai/gpt-4.1-mini`; Suporte `anthropic/claude-sonnet-5.5`; Desenvolvimento e produto `anthropic/claude-opus-5.5`; OpenRouter, temperatura 0,2, instruções padrão |
| Reranker | TEI de CPU com `BAAI/bge-reranker-v2-m3`, 8 GB de limite, 20 candidatos de até 1.100 caracteres, timeout de 60 s |
| Perguntas | as 17 do ensaio 0005 nos três níveis (51 respostas por configuração) e as 9 do ensaio 0006 pelo `ask` do MCP em Desenvolvimento e produto |

Configurações comparadas:

| Configuração | Máximo de buscas (Usuário final / Suporte / Desenvolvimento) | Reranker |
|---|---|---|
| busca única | 1 / 1 / 1 | desligado |
| etapas | 2 / 3 / 4 | desligado |
| etapas + reranker | 2 / 3 / 4 | ligado |

## Qualidade lida pelo orquestrador

Mesmo método do ensaio 0005: cada resposta classificada como útil e correta para o público do nível, falha (errada, imprecisa ou contra as instruções do nível) ou "não sei". A pergunta 11 (sem relação) fica fora da contagem; 16 perguntas por nível.

| Configuração | Usuário final | Suporte | Desenvolvimento e produto |
|---|---|---|---|
| Ensaio 0005 (busca única) | 7 / 6 / 3 | 12 / 0 / 4 | 14 / 0 / 2 |
| busca única | 6 / 7 / 3 | 11 / 0 / 5 | 13 / 0 / 3 |
| **etapas** | 4 / 9 / 3 | **15 / 0 / 1** | **16 / 0 / 0** |
| etapas + reranker | 6 / 8 / 2 | 14 / 0 / 2 | 16 / 0 / 0 |

Útil / falha / "não sei". A busca única de hoje reproduz o ensaio 0005 dentro da variação entre execuções.

| Canal | Ensaio 0006 | Com etapas |
|---|---|---|
| `ask` do MCP, Desenvolvimento e produto | 7 de 9 ("não sei" nas perguntas 5 e 9) | **9 de 9** (4 buscas nas perguntas 5 e 9) |

- **Etapas resolvem o que a busca única deixava como "não sei".** No Suporte, as perguntas 7, 13 e 16 passaram a ter resposta: a segunda ou a terceira busca achou o registro de encerramento, as regras da inscrição com exemplos de recusa e a ausência da funcionalidade nas entregas publicadas. Em Desenvolvimento e produto, as perguntas 12 e 14 (SQL) acharam a tabela de custos e o evento de auditoria com os valores anterior e novo, e a 17 achou o commit da entrega, separando o que foi feito do que ficou de fora. O `ask` do MCP passou a acertar o que só o cliente MCP, buscando sozinho, acertava no ensaio 0006.
- **A pergunta 12 no Suporte continua "não sei" em todas as configurações:** o esquema do banco só está em fontes de Desenvolvimento e produto (achado 5 do ensaio 0005).
- **O Usuário final piora com etapas.** As buscas a mais trazem mais documentos internos da pasta que mistura o manual com planos e registros de execução, e o `gpt-4.1-mini` repete commits e nomes de arquivo, planeja a funcionalidade da pergunta 15 e apresenta como entregue o que só estava planejado. É o achado 3 do ensaio 0005 (separar as fontes por público) amplificado.
- **O reranker muda as citações, não a qualidade.** A citação do topo mudou em 37 de 48 respostas com fontes e o conjunto de citações em todas, mas o saldo ficou igual (Suporte 15 para 14). O único ganho claro foi a pergunta 7 do Suporte, achada com uma busca em vez de duas.
- **Nenhuma resposta de Suporte ou de Desenvolvimento e produto feriu as instruções do nível**; o Suporte recusou planejar a pergunta 15 nas três configurações.

## Custo e tempo

| Configuração | Nível | Tokens de entrada (média) | Tokens de saída (média) | Buscas (média) | Custo por resposta | Tempo (mediana) | Tempo (p95) |
|---|---|---|---|---|---|---|---|
| busca única | Usuário final | 3.880 | 201 | 1,00 | US$ 0,0019 | 3,2 s | 6,1 s |
| busca única | Suporte | 4.774 | 904 | 1,00 | US$ 0,0186 | 8,8 s | 12,9 s |
| busca única | Desenvolvimento e produto | 6.525 | 1.289 | 1,00 | US$ 0,0519 | 15,5 s | 20,9 s |
| etapas | Usuário final | 6.833 | 231 | 1,47 | US$ 0,0031 | 3,8 s | 6,2 s |
| etapas | Suporte | 16.262 | 1.060 | 2,29 | US$ 0,0431 | 12,1 s | 20,2 s |
| etapas | Desenvolvimento e produto | 20.170 | 1.818 | 1,94 | US$ 0,1170 | 19,5 s | 43,2 s |
| etapas + reranker | Usuário final | 6.761 | 250 | 1,47 | US$ 0,0031 | 51,1 s | 96,3 s |
| etapas + reranker | Suporte | 14.967 | 1.026 | 2,12 | US$ 0,0402 | 82,3 s | 153,2 s |
| etapas + reranker | Desenvolvimento e produto | 19.138 | 1.774 | 1,88 | US$ 0,1120 | 66,2 s | 204,7 s |

- Etapas custam cerca de duas vezes a busca única por resposta, porque cada busca a mais leva os trechos novos ao modelo; o tempo sobe de 3 a 4 segundos na mediana.
- O reranker em CPU somou de 40 a 70 segundos por resposta (cada busca reordenada leva dezenas de segundos) e ocupou 5,9 GB. Todas as buscas com trechos foram reordenadas, sem queda para a ordem do RRF.
- O `ask` do MCP com etapas custou US$ 0,156 por resposta (US$ 0,053 no ensaio 0006).

## Conjunto sintético com LLM real

Stack isolada (`knobridge-eval`), corpus do Vértice ERP e as 30 perguntas de `scripts/eval/`, com `gpt-4.1-mini` no Usuário final e no Suporte e `gpt-4.1` em Desenvolvimento e produto, reranker desligado.

| Execução | Corretas | Vazamentos | Buscas (média) | Custo total | Latência p50 |
|---|---|---|---|---|---|
| busca única (1/1/1) | 29 de 30 | 0 | 1,00 | US$ 0,066 | 2,2 s |
| etapas (2/3/4) | 28 de 30 | 0 | 1,13 | US$ 0,075 | 2,4 s |

O corpus sintético é pequeno (24 documentos em pastas, 10 chamados e 8 cards) e a busca única já acerta quase tudo, inclusive as 5 perguntas marcadas como de várias buscas: o conjunto serve para provar o caminho, o filtro de nível (nenhum vazamento) e o aviso de arquivos dominantes (`gerado/**` com 95,5% dos trechos da fonte de código), mas não mede o ganho das etapas. A pergunta que mudou (Suporte, "já está em desenvolvimento?") variou entre execuções; a errada nas duas (Usuário final) faltou um termo obrigatório do gabarito. Perguntas mais difíceis, com a resposta espalhada em mais de um documento, ficam como próximo passo do conjunto.

## Achados e correções

1. **Os modelos Claude 5.5 recusam `tool_choice` forçado** (400 pelo OpenRouter). A busca inicial vazia usava `required` para obrigar o modelo a buscar de novo. Correção (decisão D27): só `auto` ou `none`, com a linha das fontes pedindo nova busca com outra formulação.
2. **Reranker opcional e desligado por padrão** (decisão D25, [ADR 0011](../adr/0011-reranker-opcional.md)): em CPU ele não cabe nos 4 GB previstos e não melhorou a qualidade neste índice. Fica atrás do perfil `reranker` do compose; um cross-encoder menor em ONNX fica para um plano futuro.
3. **Usuário final com 1 busca por padrão** (decisão D29): as etapas ajudam Suporte e Desenvolvimento e prejudicam o modelo pequeno com fontes mistas. Os padrões passam a 1, 3 e 4.
4. **A pergunta sem relação gastava buscas pagas** e, em Desenvolvimento e produto, terminava como resposta concluída com uma citação solta, com o texto de "sem fonte" copiado pelo modelo; 19 respostas do ensaio copiaram esse texto com citações anexadas. Correção (decisão D30): uma única reformulação quando a busca inicial volta vazia, e resposta sem nenhum marcador `[n]` fica sem citações e com status de sem fonte.
5. **O botão Testar parecia não fazer nada** no teste do usuário com a chave nova (decisão D31): o resultado passa a aparecer junto do botão.

## Gasto

| Item | Custo |
|---|---|
| 159 respostas do chat nas três configurações (153 mais 6 repetições das falhas) | US$ 6,71 |
| 9 respostas do `ask` do MCP | US$ 1,40 |
| Conjunto sintético, duas execuções de 30 perguntas | US$ 0,14 |
| **Total** | **cerca de US$ 8,25** |

## Como repetir

```bash
# stack do Minski com o código atual (portas próprias; a pasta de fontes aponta para os repositórios)
KNOBRIDGE_SOURCES_DIR=<pasta com os repositórios> API_PORT=28000 ... docker compose -p knobridge-minski up -d --build --wait
# com o reranker:
KNOBRIDGE_RERANKER_URL=http://reranker:80 KNOBRIDGE_RERANKER_TIMEOUT=60 KNOBRIDGE_RERANKER_CANDIDATES=20 \
  KNOBRIDGE_RERANKER_MAX_CHARS=1100 docker compose -p knobridge-minski --profile reranker up -d --wait
# painel: Configurações > Níveis de resposta (modelo e máximo de buscas) > Produtos (Reordenar trechos) > Chat
# conjunto sintético: docs/guias/avaliar-respostas.md (seção "Medir com um provedor real")
```
