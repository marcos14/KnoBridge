# Ensaio real do harness com runner local: Claude Code x Codex no projeto Minski

> 2026-10-11 · Plano [0004](../planos/0004-harness-runner-local.md), subfase F5.2 · executado pelo orquestrador na stack local `knobridge-minski` e no runner da máquina do usuário, fora da CI

Primeiro uso do harness de código com conteúdo real: três módulos do projeto Minski, do próprio usuário, mapeados pelo `knobridge-runner` com o Claude Code e com o Codex, já logados por assinatura na máquina. Depois, as perguntas do [ensaio 0001](0001-ensaio-minski.md) foram refeitas com o conhecimento gerado no índice. Pela regra 9, este relatório traz só métricas, as perguntas e conclusões, sem trechos do código, dos itens gerados ou das respostas. Nada do Minski entrou no repositório.

## Configuração

| Item | Valor |
|---|---|
| Stack | `deploy/docker-compose.yml`, projeto `knobridge-minski`, com o índice do ensaio 0001 (20.485 chunks) e as migrações `0014`/`0015` aplicadas por cima |
| Runner | `knobridge-runner` 0.1 em Windows 11, `run` com concorrência 1, config própria do ensaio (`--config`), repositórios `maestro` e `runtime` |
| Executores | Claude Code 2.1.296, sem modelo na fonte (o padrão do CLI foi `claude-opus-5-5`); Codex CLI 0.142.5 com `gpt-5.5` (o padrão do `~/.codex` exige CLI mais novo) |
| Fontes | duas fontes `runner` na mesma coleção do ensaio 0001: orçamento de US$ 5 por tarefa, tempo limite de 1800 s, 30 linhas de excerto, sem disparo por commit |
| Módulos (D13) | `apps/web/src/lib/ai-budget` (2 arquivos, 201 linhas, TypeScript), `apps/web/src/lib/people` (12 arquivos, 2.715 linhas, TypeScript) e `internal/answers` (6 arquivos, 833 linhas, Go) |
| Chat | assistente do ensaio 0001 (`openai/gpt-6-luna-pro` pelo OpenRouter, similaridade mínima 0,35) |

O relatório do runner sugeriu 153 módulos no `maestro` e 35 no `runtime`; os três escolhidos estavam entre eles com exatamente esses padrões, então nenhum módulo manual foi preciso.

## Tarefas

Uma tarefa por módulo e executor, disparadas pela API do painel, em fila e uma de cada vez. A rodada 2 do Claude repetiu a 1 depois das correções 1 a 3 (seção "Achados").

| Executor | Módulo | Duração | Tokens (entrada / saída) | Custo (US$) | Aceitos | Rejeitados |
|---|---|---|---|---|---|---|
| Claude, rodada 1 | ai-budget | 56 s | 84 mil / 6,9 mil | 0,36 | 11 | 4 `symbol_mismatch` |
| Claude, rodada 1 | people | 100 s | 186 mil / 12,9 mil | 0,64 | 20 | 5 `symbol_mismatch` |
| Claude, rodada 1 | answers | 84 s | 71 mil / 10,7 mil | 0,37 | 18 | 0 |
| Codex | ai-budget | 183 s | 202 mil / 9,3 mil | — | 16 | 0 |
| Codex | people | 330 s | 644 mil / 16,0 mil | — | 21 | 0 |
| Codex | answers | 290 s | 253 mil / 15,1 mil | — | 24 | 0 |
| Claude, rodada 2 | ai-budget | 65 s | 161 mil / 7,9 mil | 0,29 | 12 | 0 |
| Claude, rodada 2 | people | 110 s | 135 mil / 13,7 mil | 0,52 | 24 | 2 `range_too_long` |
| Claude, rodada 2 | answers | 87 s | 96 mil / 11,1 mil | 0,35 | 16 | 0 |

- **Totais por rodada**: Claude, 4 min e cerca de US$ 1,2 a 1,4, com 49 a 52 itens; Codex, 13 min 23 s e 1,1 milhão de tokens de entrada, com 61 itens. O custo do Claude é a estimativa do CLI; com assinatura, o limite real é a franquia. O custo do Codex fica em branco porque o runner só o estima com preço configurado (`[pricing.codex]`).
- **Falhas, adiamentos e trava de ferramenta**: nenhum nas 9 tarefas. Nenhuma tentativa de ferramenta fora da lista, nem `unsafe_tool_use`, nem resgate.
- **Indexação depois de cada resultado**: 9 sincronizações `harness`, de 3 a 4 s cada, US$ 0,002 em embeddings no total.

## Qualidade dos itens (leitura do orquestrador)

Conferi uma amostra contra o código: 12 afirmações do Claude e 4 próprias do Codex, entre limites, padrões, ordem de verificação, validações e intervalos. **As 16 estavam corretas**, com evidências que apontavam para as linhas certas. Os dois executores cobriram as mesmas regras centrais de cada módulo; as diferenças estão no estilo:

| Aspecto | Claude Code | Codex |
|---|---|---|
| Regras / enriquecimento | 46 / 3 | 58 / 3 |
| Termo de código (crase) no enunciado | 4 de 46 | 18 de 58 |
| Classificação | 41 intencional, 5 observado | 5 intencional, 53 observado |
| Evidências por regra | 1,7 | 1,8 |
| Regras com mensagem exibida | 16 | 24 |

O Claude escreve na linguagem de quem usa o sistema e lê os comentários de projeto como intenção. O Codex é mais granular: transforma cada validação em regra, fala mais em termos do código e só marca como intencional o que está declarado. As 9 rejeições da rodada 1 do Claude eram citações corretas recusadas pela verificação (achado 3); depois da correção, sobraram 2 rejeições legítimas, de citações da função inteira com mais de 80 linhas.

## Perguntas

As 11 perguntas do ensaio 0001, com similaridade mínima 0,35 e a coleção com o conhecimento dos três módulos (rodada 2 do Claude). Rodadas duas vezes: antes e depois da correção 4.

| # | Tipo | Pergunta | Ensaio 0001 | Depois do harness e da correção 4 |
|---|---|---|---|---|
| 1 | como funciona | Como funciona o teto de gasto com IA por Work Item? | correta | correta, citando só itens de conhecimento, e com o que o Owner faz para liberar |
| 2 | como funciona | O que faz o comando `maestro attest` e quando ele é usado? | correta | correta |
| 3 | como funciona | Como o Runtime é inscrito numa organização da plataforma? | correta | correta |
| 4 | por que | Por que todo modelo usado precisa ter preço em `LLM_MODEL_PRICES`? | correta | correta |
| 5 | por que | Por que o rebaixamento de papel avisa o usuário e o que motivou essa regra? | "não sei" | **correta**: o item de conhecimento explica o aviso, e as decisões e o commit trazem o motivo |
| 6 | quando | Quando e como foi corrigido o texto "US5,00" na ajuda do teto de gasto? | correta | correta |
| 7 | quando | O que mudou no Runtime na versão V3 em relação ao `observe --watch`? | correta | correta |
| 8 | onde no código | Em que arquivo fica a tabela de preços embutida dos modelos de LLM? | correta | correta |
| 9 | onde no código | Onde no código do Runtime é tratado o comando `answers --wait`? | correta | correta, com o arquivo e a função |
| 10 | como funciona | Quais são as etapas do ciclo de um Work Item, de Intent até DONE? | correta | correta |
| 11 | sem relação | Qual é a receita tradicional de feijoada? | sem fonte | sem fonte, sem chamar o LLM, em 0,9 s |

- **Respondidas com citação verificável**: 10 de 10 perguntas sobre o projeto (eram 9). Itens de conhecimento apareceram entre as fontes de 4 perguntas e foram citados nas respostas 1 e 5.
- **Antes da correção 4**, a pergunta 5 continuava em "não sei", embora o item que a responde já estivesse no índice (achado 4).
- **Latência mediana**: 7,8 s. **Tokens de chat por rodada**: cerca de 148 mil de entrada e 7 mil de saída.
- **Gasto do ensaio na chave do OpenRouter** (embeddings e as duas rodadas de perguntas): cerca de US$ 0,05. As tarefas do harness foram pela assinatura dos CLIs.

## Achados e correções

Cada correção entrou com teste na mesma subfase.

1. **`doctor` com falso aviso no Windows em português**: o `icacls` escreve na página de código OEM do console, e "BUILTIN\Usuários" chegava com o acento trocado. Por isso o aviso de que o sandbox do Codex não lê o checkout aparecia mesmo com a permissão certa. Corrigido com um padrão que tolera o acento trocado.
2. **Modelo do Claude não registrado**: sem modelo na fonte, o CLI informa o padrão como `claude-opus-5-5[1m]` (a variante de contexto de 1M). Os colchetes não passam no formato de nome do protocolo, e a tarefa ficava com modelo vazio. Agora o runner tira o sufixo entre colchetes; a rodada 2 já mostra `claude-opus-5-5`.
3. **Verificação recusava citações corretas em funções longas**: o símbolo só era procurado até 50 linhas acima do intervalo, e as funções do Minski têm corpo maior. Resultado: 9 de 58 itens do Claude recusados (16%). Agora a verificação também sobe pelas declarações que envolvem o intervalo, pela indentação, até 400 linhas, e para em escopo encerrado, de modo que uma função vizinha não conta ([harness.md](../specs/harness.md)). Nos 9 casos reais, todos passam; um símbolo errado continua recusado.
4. **Busca vetorial perdia o trecho mais próximo** (vem do plano 0003): com `hnsw.ef_search` 100, o índice HNSW devolvia vizinhos com similaridade até 0,47 para a pergunta 5, e o item que a responde tem 0,60. Só com `limit` 50 o planner trocava para a varredura exata e o achava. Medida de recall@10 contra a varredura exata, com consultas fora do índice: 0,90 com 100, 0,95 com 200, 0,97 com 400 e 0,98 com 1000. A busca passou a usar 1000, o máximo do pgvector ([indexacao.md](../specs/indexacao.md)); a pergunta 5 passou a ser respondida.
5. **Codex no Windows lê arquivos pelo PowerShell com acentos trocados**: nos registros locais, o texto UTF-8 aparece decodificado como página de código do Windows. Os excertos não são afetados, porque o runner os tira do arquivo, e os itens saíram corretos. Mas é ruído para o modelo. Não corrigido; candidato a investigar com o Codex num terminal UTF-8.
6. **Relatórios gerados continuam dominando o índice**, como no ensaio 0001: com a busca antiga, os primeiros resultados da pergunta 5 eram todos de `docs/resumos`. A recomendação de excluir artefatos gerados com `exclude_globs` continua valendo.
7. **Ambiente**: ao recriar os contêineres da stack depois de uma pausa, o DNS interno do Docker parou de resolver `postgres`. Um `docker compose ... down` (sem `-v`, mantendo os volumes) seguido de `up` resolveu.

## Recomendação

**Executor padrão: Claude Code**, como já é o padrão da fonte. Nos três módulos ele foi cerca de 3 vezes mais rápido e usou cerca de um terço dos tokens de entrada. Escreve as regras na linguagem do usuário, que é o que o chat devolve, e com as correções 2 e 3 não teve rejeição indevida. **Codex como alternativa**: mais granular nas validações e sem rejeições, bom para módulos de regras de entrada, mas mais lento e mais técnico no texto. Para comparar custos com chave de API, configure o preço do modelo do Codex no runner.

Para quem vai usar: comece pelo modelo padrão do CLI e por módulos de até alguns milhares de linhas. Numa assinatura, uma tarefa de módulo custa de US$ 0,30 a 0,65 na estimativa do Claude, bem abaixo do orçamento padrão de US$ 5.

## Como repetir

```bash
export KNOBRIDGE_SOURCES_DIR=/caminho/da/pasta   # a stack do ensaio 0001
docker compose -p knobridge-minski -f deploy/docker-compose.yml up -d --build --wait
# painel: Runners > Novo runner; na máquina com o código:
uv tool install ./runner
knobridge-runner configure --server-url http://localhost:8000 --repo maestro=/caminho/do/checkout
knobridge-runner doctor && knobridge-runner run
# painel: Fontes > Nova fonte (Runner local) > Módulos > rodar com Claude Code e com Codex
```

Passo a passo em [docs/guias/mapear-codigo-com-runner.md](../guias/mapear-codigo-com-runner.md).
