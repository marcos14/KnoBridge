# Avaliação `teste`

- Início: 2026-10-20T14:00:00Z; fim: 2026-10-20T14:05:00Z
- Stack: `kb.test`
- Perguntas: `perguntas.json` (sha256 `5a6cbd941a28`), 1 repetição(ões)
- Modelo de embedding: `fake-embedding`; limiar efetivo: fake-embedding: 0,35
- Reranker: ligado

| Nível | Modelo | Etapas máximas |
|---|---|---|
| Usuário final | fake-chat | 2 |
| Suporte | fake-chat | 3 |
| Desenvolvimento e produto | fake-chat | 2 |

## Resumo

| Nível | Respostas | Corretas | Não sei | Erradas | Vazamentos | Erros | Acerto | Recall de fonte | Etapas (média) | Custo total (US$) | Custo médio (US$) | Latência p50 (ms) | Latência p95 (ms) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Usuário final | 2 | 2 | 0 | 0 | 0 | 0 | 100,0% | 100,0% | 1,00 | 0,0030 | 0,0015 | 100 | 300 |
| Suporte | 2 | 0 | 0 | 1 | 1 | 0 | 0,0% | 0,0% | 1,50 | 0,0010 | 0,0010 | 200 | 900 |
| Desenvolvimento e produto | 2 | 0 | 1 | 0 | 0 | 1 | 0,0% | 0,0% | 1,00 | 0,0010 | 0,0010 | 100 | 100 |
| Total | 6 | 2 | 1 | 1 | 1 | 1 | 33,3% | 20,0% | 1,20 | 0,0050 | 0,0013 | 200 | 900 |

## Perguntas que pedem mais de uma busca

| Nível | Respostas | Corretas | Não sei | Erradas | Vazamentos | Erros | Acerto | Recall de fonte | Etapas (média) | Custo total (US$) | Custo médio (US$) | Latência p50 (ms) | Latência p95 (ms) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Usuário final | 0 | 0 | 0 | 0 | 0 | 0 | — | — | — | — | — | — | — |
| Suporte | 1 | 0 | 0 | 1 | 0 | 0 | 0,0% | 0,0% | 2,00 | — | — | 900 | 900 |
| Desenvolvimento e produto | 1 | 0 | 1 | 0 | 0 | 0 | 0,0% | 0,0% | 1,00 | 0,0010 | 0,0010 | 100 | 100 |
| Total | 2 | 0 | 1 | 1 | 0 | 0 | 0,0% | 0,0% | 1,50 | 0,0010 | 0,0010 | 100 | 900 |

## Índice

| Fonte | Tipo | Documentos | Trechos | Arquivos dominantes |
|---|---|---|---|---|
| eval-teste-manual | folder | 3 | 7 | — |
| eval-teste-interno | folder | 3 | 7 | — |
| eval-teste-codigo | folder | 3 | 40 | gerado/** (60,0%) |
| eval-teste-chamados | tickets | 3 | 7 | — |
| eval-teste-cards | cards | 3 | 7 | — |

## Respostas

| Pergunta | Nível | Veredito | Etapas | Custo (US$) | Latência (ms) | Citações |
|---|---|---|---|---|---|---|
| eu-01 #1 | Usuário final | correta | 1 | 0,0020 | 300 | manual-boleto.md#L1-L9 |
| eu-09 #1 | Usuário final | correta | 1 | 0,0010 | 100 | — |
| su-01 #1 | Suporte | errada | 2 | — | 900 | ticket:EVAL-T-001 |
| su-02 #1 | Suporte | vazamento | 1 | 0,0010 | 200 | card:EVAL-C-002 |
| pd-01 #1 | Desenvolvimento e produto | erro | — | — | — | — |
| pd-02 #1 | Desenvolvimento e produto | não sei | 1 | 0,0010 | 100 | — |

## Respostas não corretas

### su-01 #1 (Suporte): errada

> Consulta de limite estourado?

Resposta: Veja o chamado [1].

### su-02 #1 (Suporte): vazamento

> Qual validação trava o pedido?

Resposta: O card [1] explica.

### pd-01 #1 (Desenvolvimento e produto): erro

> Onde fica a exposição?

Erro: `level_not_configured`

### pd-02 #1 (Desenvolvimento e produto): não sei

> A tolerância foi entregue?

Resposta: Não encontrei essa informação nas fontes que tenho disponíveis.
