# Embeddings em pt-BR: OpenAI x Gemini

> 2026-10-12 · Plano [0005](../planos/0005-chamados-por-api.md), subfase F6.3 · executado pelo orquestrador na stack local do [ensaio 0003](0003-ensaio-chamados-sinteticos.md), fora da CI

Comparação de três modelos de embedding sobre o mesmo conteúdo em pt-BR: o padrão atual, `openai/text-embedding-3-small`, contra dois do Gemini pelo OpenRouter, ambos com 1536 dimensões para caber no índice (`vector(1536)`). Cobre o item da Fase 0 da visão "comparação OpenAI x Gemini embedding em pt-BR". Todo o conteúdo é sintético, gerado por `scripts/synthetic_tickets` (semente 7).

## Configuração

| Item | Valor |
|---|---|
| Conteúdo por coleção | 300 chamados (fonte `tickets`, por upload, anonimizados) e 30 artigos de produto em Markdown (fonte de pasta): 24 artigos de solução e 6 visões gerais de módulo que servem de distratores. Total de 330 documentos por coleção. |
| Modelos | `openai/text-embedding-3-small` (1536 nativo), `google/gemini-embedding-001` e `google/gemini-embedding-2` (3072 nativo, pedidos com `dimensions: 1536`) |
| Perguntas | 48 perguntas de suporte (2 por problema, descrevendo o sintoma sem o código do erro) e 5 sem relação (feijoada, Copa de 1970, capital da Austrália, trocar pneu, previsão do tempo) |
| Relevante | o artigo do problema ou qualquer chamado resolvido ou fechado do mesmo problema |
| Medição | rota "testar busca" (busca híbrida completa: vetor + FTS + RRF), `limit` 10, similaridade mínima 0 |

## Resultados

| Modelo | recall@5 | recall@10 | MRR@10 | artigo no top 5 | Indexação | Custo dos 330 documentos | Busca (mediana) |
|---|---|---|---|---|---|---|---|
| `openai/text-embedding-3-small` | 0,958 | 0,979 | 0,890 | 0,688 | 36 s | US$ 0,003 | 0,8 s |
| `google/gemini-embedding-001` | **1,000** | **1,000** | 0,941 | **0,917** | 62 s | US$ 0,022 | 1,3 s |
| `google/gemini-embedding-2` | **1,000** | **1,000** | **0,953** | 0,646 | 43 s | US$ 0,029 | 0,9 s |

Similaridade vetorial do melhor trecho de cada pergunta:

| Modelo | Perguntas relacionadas (mín · mediana · máx) | Sem relação (mín · máx) | Folga |
|---|---|---|---|
| `openai/text-embedding-3-small` | 0,475 · 0,587 · 0,692 | 0,163 · 0,302 | 0,17 |
| `google/gemini-embedding-001` | 0,682 · 0,761 · 0,826 | 0,488 · 0,544 | 0,14 |
| `google/gemini-embedding-2` | 0,594 · 0,757 · 0,822 | 0,509 · 0,552 | 0,04 |

- O OpenAI perdeu 2 das 48 perguntas no top 5. Uma delas é a paráfrase que também falhou no chat do ensaio 0003 ("As vendas no débito e no crédito não passam no caixa…", problema da TEF sem comunicação), que o OpenAI não achou nem no top 10. Os dois Gemini acharam as duas em 1º lugar.
- O `gemini-embedding-001` foi o que mais achou o **artigo** de solução (92% no top 5, contra 69% do OpenAI). O `gemini-embedding-2` ranqueou melhor os chamados (maior MRR), mas achou menos artigos.
- Custo: o OpenAI cobra US$ 0,02 por milhão de tokens; os Gemini, US$ 0,15 (`001`) e US$ 0,20 (`2`). O custo absoluto segue pequeno: o índice inteiro do Minski (9 milhões de tokens) custaria cerca de US$ 1,35 com o `001`, contra US$ 0,18 com o OpenAI.

## O limiar de similaridade muda com o modelo

O limiar padrão de 0,35 foi calibrado para o OpenAI no [ensaio 0001](0001-ensaio-minski.md) e continua certo para ele: as perguntas sem relação ficam em até 0,30. Com os Gemini, **todas as perguntas sem relação passam de 0,48**. Com 0,35, o assistente chamaria o LLM com fontes irrelevantes em vez de responder "sem fonte" (regra 8). Neste conteúdo, o limiar que separa os dois grupos fica em torno de **0,60** para o `gemini-embedding-001`. Para o `gemini-embedding-2`, a folga é de só 0,04 (0,552 contra 0,594), apertada demais para um valor fixo seguro.

Por isso, quem criar uma coleção com o Gemini hoje precisa ajustar a similaridade mínima do assistente (cerca de 0,60 com o `001`). A nota está em [indexacao.md](../specs/indexacao.md).

## Achado e correção

**O `gemini-embedding-2` recusava os lotes de indexação.** A API do Google aceita no máximo 100 textos por lote ("at most 100 requests can be in one batch"), e o KnoBridge mandava até 128. O OpenRouter repassa a recusa no `gemini-embedding-2` (o `001` passou porque o OpenRouter o encaminha por outro caminho). A conferência da F5.1, com uma frase só, não pegou isso. Agora os modelos Gemini usam lotes de até 100 textos, com teste.

## Recomendação

1. **Manter `openai/text-embedding-3-small` como padrão por enquanto.** A recuperação é quase a mesma no top 10 (98% contra 100%), o custo é 7 a 10 vezes menor e o limiar já está calibrado.
2. **O `gemini-embedding-001` é a melhor opção de qualidade** em paráfrases e na recuperação do artigo de solução, e é o candidato a novo padrão. Antes da troca:
   - a similaridade mínima precisa passar a ter um padrão por modelo (cerca de 0,60 para o `001`), para não quebrar a regra 8;
   - a comparação precisa ser repetida no índice real do Minski, com as perguntas dos ensaios 0001 e 0002, porque o conteúdo sintético vem de modelos de texto e pode favorecer um ou outro modelo.

   Se as duas coisas confirmarem, a troca do padrão ganha um ADR.
3. **Não usar o `gemini-embedding-2` por enquanto.** A folga entre perguntas relacionadas e sem relação é pequena demais, e ele achou menos artigos que o `001`.

## Custo

Gasto da comparação na chave do OpenRouter (três indexações de 330 documentos, a primeira tentativa do `gemini-embedding-2` e as 159 buscas): **US$ 0,08**.

## Como repetir

```bash
cd scripts && uv run python -m synthetic_tickets --seed 7 --tickets 300 --out ../../kb-sinteticos
# stack do ensaio 0003 com os artigos (kb-sinteticos/docs) montados em /sources;
# uma coleção por modelo, cada uma com a fonte de chamados (upload do tickets.jsonl) e a de pasta (/sources);
# perguntas.json pela rota "testar busca" com limit 10 e similaridade mínima 0
```
