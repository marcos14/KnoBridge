# Comparação: `teste` (A) x `depois` (B)

## Configuração

| Opção | A | B |
|---|---|---|
| `rerank` | true | false |

## Resumo

| Nível | Métrica | A | B | Diferença |
|---|---|---|---|---|
| Usuário final | Respostas | 2 | 2 | 0 |
| Usuário final | Acerto | 100,0% | 50,0% | -50,0 p.p. |
| Usuário final | Recall de fonte | 100,0% | 100,0% | 0,0 p.p. |
| Usuário final | Taxa de "não sei" | 0,0% | 0,0% | 0,0 p.p. |
| Usuário final | Vazamentos | 0 | 0 | 0 |
| Usuário final | Etapas (média) | 1,00 | 1,00 | 0,00 |
| Usuário final | Custo médio (US$) | 0,0015 | 0,0015 | 0,0000 |
| Usuário final | Latência p50 (ms) | 100 | 100 | 0 |
| Suporte | Respostas | 2 | 2 | 0 |
| Suporte | Acerto | 0,0% | 0,0% | 0,0 p.p. |
| Suporte | Recall de fonte | 0,0% | 0,0% | 0,0 p.p. |
| Suporte | Taxa de "não sei" | 0,0% | 0,0% | 0,0 p.p. |
| Suporte | Vazamentos | 1 | 1 | 0 |
| Suporte | Etapas (média) | 1,50 | 1,50 | 0,00 |
| Suporte | Custo médio (US$) | 0,0010 | 0,0010 | 0,0000 |
| Suporte | Latência p50 (ms) | 200 | 200 | 0 |
| Desenvolvimento e produto | Respostas | 2 | 2 | 0 |
| Desenvolvimento e produto | Acerto | 0,0% | 50,0% | +50,0 p.p. |
| Desenvolvimento e produto | Recall de fonte | 0,0% | 50,0% | +50,0 p.p. |
| Desenvolvimento e produto | Taxa de "não sei" | 50,0% | 0,0% | -50,0 p.p. |
| Desenvolvimento e produto | Vazamentos | 0 | 0 | 0 |
| Desenvolvimento e produto | Etapas (média) | 1,00 | 3,00 | +2,00 |
| Desenvolvimento e produto | Custo médio (US$) | 0,0010 | 0,0010 | 0,0000 |
| Desenvolvimento e produto | Latência p50 (ms) | 100 | 100 | 0 |
| Total | Respostas | 6 | 6 | 0 |
| Total | Acerto | 33,3% | 33,3% | 0,0 p.p. |
| Total | Recall de fonte | 20,0% | 40,0% | +20,0 p.p. |
| Total | Taxa de "não sei" | 20,0% | 0,0% | -20,0 p.p. |
| Total | Vazamentos | 1 | 1 | 0 |
| Total | Etapas (média) | 1,20 | 1,60 | +0,40 |
| Total | Custo médio (US$) | 0,0013 | 0,0013 | 0,0000 |
| Total | Latência p50 (ms) | 200 | 200 | 0 |

## Perguntas que mudaram de veredito

| Pergunta | Nível | A | B | Etapas (A → B) | Custo médio US$ (A → B) |
|---|---|---|---|---|---|
| eu-09 | Usuário final | correta | errada | 1,00 → 1,00 | 0,0010 → 0,0010 |
| pd-02 | Desenvolvimento e produto | não sei | correta | 1,00 → 3,00 | 0,0010 → 0,0010 |
