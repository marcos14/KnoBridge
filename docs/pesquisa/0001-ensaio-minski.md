# Ensaio real de indexação e chat com o projeto Minski

> 2026-10-11 · Plano [0003](../planos/0003-primeiro-conhecimento.md), subfase F6.3 · executado pelo orquestrador na stack local, fora da CI

Primeiro uso do KnoBridge com conteúdo real: um projeto do próprio usuário (Minski), lido de `C:\Projetos\Minski` montado somente leitura em `/sources`. Nada do conteúdo do Minski entrou no repositório; este relatório traz métricas e as perguntas, sem trechos das respostas nem das fontes.

## Configuração

| Item | Valor |
|---|---|
| Stack | `deploy/docker-compose.yml` local, `KNOBRIDGE_SOURCES_DIR=C:/Projetos/Minski` |
| Provedor | OpenRouter (tipo `openrouter`, chave do usuário cadastrada pelo painel/API, cifrada) |
| Embedding | `openai/text-embedding-3-small` (1536 dimensões) |
| LLM do assistente | `openai/gpt-6-luna-pro`, temperatura 0,2 |
| Fontes | Git `MINSKI-MAESTRO` (TypeScript/Next), Git `MINSKI-MAESTRO-RUNTIME` (Go), pasta `/sources` com `include_globs` `/*.md` e `/*.pdf` (documentos soltos da raiz) |
| Exclusões | só as padrão (`.gitignore`, binários, zips, lockfiles, limites); nenhum glob de exclusão extra |

## Sincronizações

| Fonte | Documentos | Arquivos / commits | Chunks | Tokens de embedding | Custo (US$) | Duração |
|---|---|---|---|---|---|---|
| MINSKI-MAESTRO | 2.106 | 1.906 / 200 | 17.742 | 7.958.207 | 0,159 | 14 min 52 s |
| MINSKI-MAESTRO-RUNTIME | 312 | 238 / 74 | 1.987 | 838.526 | 0,017 | 2 min 25 s |
| Documentos soltos | 15 | 15 / — | 593 | 258.441 | 0,005 | 48 s |
| **Total, 1ª sincronização** | **2.433** | | **20.322** | **9.055.174** | **0,181** | as três em paralelo |
| 2ª sincronização (sem mudanças) | 0 novos, 0 alterados, 0 removidos | | 0 | 0 | 0,000 | 12 s cada |

- Nenhum documento com erro nas três fontes (inclui dois PDFs de ~1,6 MB convertidos pelo MarkItDown).
- Linguagens dos arquivos: TypeScript 1.008, TSX 379, Markdown 217, Go 197, JSON 122, shell 61, YAML 39, SQL 24, HTML 20, JavaScript 17.
- Onde ficaram os chunks: `apps/web` 6.941; `docs/resumos` 4.661 (apenas 34 arquivos JSON/Markdown de relatórios gerados, 23% de todos os chunks); `docs/avaliacao` 1.697; `DECISIONS.md` 1.001.
- O incremental funcionou como esperado: a segunda execução listou as mudanças, não achou nenhuma e terminou sem chamar o provedor de embedding.

## Perguntas

Onze perguntas, dez sobre o projeto (como funciona, por que foi decidido, quando mudou, onde fica no código) e uma sem relação. Rodadas duas vezes: com a similaridade mínima padrão (0,30) e com 0,35.

| # | Tipo | Pergunta | Citou fonte? | Qualidade (leitura do orquestrador) |
|---|---|---|---|---|
| 1 | como funciona | Como funciona o teto de gasto com IA por Work Item? | sim | correta e completa |
| 2 | como funciona | O que faz o comando `maestro attest` e quando ele é usado? | sim | correta |
| 3 | como funciona | Como o Runtime é inscrito numa organização da plataforma? | sim (PDF do manual) | correta |
| 4 | por que | Por que todo modelo usado precisa ter preço em `LLM_MODEL_PRICES`? | sim | correta, com a nuance da tabela embutida |
| 5 | por que | Por que o rebaixamento de papel avisa o usuário e o que motivou essa regra? | não (respondeu "não sei") | as fontes recuperadas não traziam o motivo; recusa correta |
| 6 | quando | Quando e como foi corrigido o texto "US5,00" na ajuda do teto de gasto? | sim (commit e DECISIONS) | correta, com o commit |
| 7 | quando | O que mudou no Runtime na versão V3 em relação ao `observe --watch`? | sim (commits) | correta e honesta sobre o escopo da mudança |
| 8 | onde no código | Em que arquivo fica a tabela de preços embutida dos modelos de LLM? | sim | correta (arquivo exato) |
| 9 | onde no código | Onde no código do Runtime é tratado o comando `answers --wait`? | sim | correta (arquivo e função) |
| 10 | como funciona | Quais são as etapas do ciclo de um Work Item, de Intent até DONE? | sim | correta |
| 11 | sem relação | Qual é a receita tradicional de feijoada? | — | com 0,30: 1 chunk passou do limiar (similaridade 0,300) e o LLM foi chamado (recusou responder); com 0,35: "sem fonte" sem chamar o LLM, em 1 s |

- Respostas com citação verificável: 9 de 10 perguntas sobre o projeto; a décima foi uma recusa correta.
- Latência mediana da resposta: 7,3 s (0,35) a 9,0 s (0,30); pergunta sem fonte: 1 s.
- Tokens de chat por rodada de 11 perguntas: ~160 mil de entrada e ~7 mil de saída (≈ US$ 0,02).
- Gasto total do ensaio na chave do OpenRouter (embeddings das duas sincronizações e as duas rodadas de perguntas): **US$ 0,21**.

## Calibração do limiar de similaridade

Maior similaridade vetorial (cosseno) entre a pergunta e os chunks, pela rota "testar busca" com limiar 0:

| Grupo | Faixa da maior similaridade |
|---|---|
| 10 perguntas sobre o projeto | 0,364 a 0,664 |
| 5 perguntas sem relação (feijoada, Copa de 1970, capital da Austrália, trocar pneu, previsão do tempo) | 0,196 a 0,300 |

O padrão de 0,30 fica exatamente na fronteira; 0,35 separa os dois grupos neste conteúdo. **Recomendação aplicada no plano**: subir o padrão (busca e assistente) para 0,35 com `text-embedding-3-small`, mantendo o valor configurável por assistente.

## Achados e recomendações

1. **Limiar padrão**: de 0,30 para 0,35 (acima). Com outro modelo de embedding o valor precisa ser medido de novo.
2. **Relatórios gerados dominam o índice**: 34 arquivos de `docs/resumos` geraram 23% dos chunks e apareceram entre as fontes de algumas respostas sem acrescentar nada. Recomendação para quem cadastra a fonte: excluir pastas de artefatos gerados com `exclude_globs` (aqui, `docs/resumos/**`). Candidato a melhoria futura: aviso na tela de documentos indexados sobre arquivos com muitos chunks.
3. **Commits com lista de arquivos duplicada**: o Markdown de cada commit repetia a lista de arquivos (rodapé do conector + seção do parser), gastando tokens. Corrigido com teste na mesma rodada do plano. Uma ressincronização depois da correção não reprocessou os commits já indexados (o conector Git só lista commits novos desde o cursor), então eles mantêm o Markdown antigo até a fonte ser recriada. Candidato a melhoria futura: ação "reindexar fonte" no painel.
4. **Custo**: indexar ~2,4 mil documentos (incluindo 274 commits e dois PDFs) custou US$ 0,18; uma pergunta custa ~US$ 0,002 com o Luna. O incremental torna a ressincronização praticamente gratuita.

## Como repetir

```bash
export KNOBRIDGE_SOURCES_DIR=/caminho/da/pasta   # montada somente leitura em /sources
docker compose -f deploy/docker-compose.yml up -d --build --wait
# painel: Provedores → Coleções → Fontes (Git em /sources/<repo>, pasta em /sources) → Sincronizar
# Assistentes: ligar a coleção, similaridade mínima 0,35 → Chat
```

Passo a passo em [docs/guias/indexar-uma-fonte.md](../guias/indexar-uma-fonte.md).
