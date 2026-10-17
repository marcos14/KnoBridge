# Avaliar as respostas com o conjunto sintético

> Rascunho v0.1 · 2026-10-17 · Em uso (plano 0011)

Como medir a qualidade das respostas do KnoBridge antes e depois de uma mudança (reranker, busca em etapas, limiar, modelo ou instruções de um nível) com o conjunto de avaliação sintético de `scripts/eval/`: um corpus de um ERP fictício (o Vértice ERP), 30 perguntas com gabarito nos três níveis e um roteiro que prepara um workspace pela API, indexa, pergunta e grava um relatório. O roteiro também compara dois relatórios.

Contrato completo (corpus, formato das perguntas, julgamento, métricas e relatório) em [avaliacao.md](../specs/avaliacao.md); decisão no [plano 0011](../planos/0011-qualidade-da-resposta.md) (D5) e no [ADR 0010](../adr/0010-busca-em-etapas-e-reranker.md).

> **O provedor `fake` só prova o caminho.** Com ele, a resposta é um eco da pergunta ("Fake reply to: …") e os embeddings são um saco de palavras: o relatório confere a preparação, a indexação, o aviso de arquivos dominantes, o filtro de nível (nenhum vazamento) e o formato, mas o acerto não mede nada. Para medir qualidade, rode com um provedor real ([Medir com um provedor real](#medir-com-um-provedor-real)).

## Pré-requisitos

- Docker com Compose v2 e memória para uma stack do KnoBridge ([subir-ambiente.md](subir-ambiente.md#pré-requisitos)).
- [uv](https://docs.astral.sh/uv/) no PATH. O roteiro roda de dentro de `scripts/` com `uv run python -m eval`; o `uv` instala as dependências do projeto `knobridge-scripts` na primeira vez.
- Uma **stack isolada**, só para a avaliação: o roteiro muda a configuração dos três níveis do workspace (e restaura no fim) e cria credenciais, coleção, fontes, produto e chave com o prefixo `eval-`. Não use o workspace de ninguém.
- Para medir com LLM real: a chave de um provedor (OpenRouter, OpenAI ou Anthropic) e orçamento. As 30 perguntas fazem 30 respostas por execução, cada uma com até o máximo de buscas do nível.

Todos os comandos rodam a partir da raiz do repositório, salvo quando o passo diz `cd scripts`.

## Passos

### 1. Montar o corpus em `/sources`

A stack lê as pastas de fontes de `/sources`, dentro dos contêineres `api` e `worker`. No ambiente de desenvolvimento, `/sources` é a pasta `deploy/sources/` do host (ignorada pelo Git). O `copy-corpus` copia `manual/`, `interno/` e `codigo/` do corpus para `deploy/sources/eval/`, que a stack vê como `/sources/eval`:

```bash
cd scripts
uv run python -m eval copy-corpus
cd ..
```

A saída diz quantos arquivos foram copiados. Chamados e cards não passam por aqui: o roteiro os envia por upload.

### 2. Subir uma stack isolada

O caminho mais leve para provar o roteiro é a camada de E2E por cima do compose de desenvolvimento, num projeto próprio: ela troca o reranker de verdade (2,3 GB de modelo) pelo reranker falso e fixa um ambiente que aceita o provedor `fake`. Só que ela monta em `/sources` as fixtures do E2E, e não `deploy/sources/`. Por isso, crie **fora do repositório** um terceiro arquivo de compose que devolve a pasta de fontes à `api` e ao `worker`, por exemplo `../kb-eval/eval-sources.yml`:

```yaml
# Devolve deploy/sources/ em /sources quando a camada de E2E está ligada (os volumes se juntam
# pelo caminho no contêiner, então este substitui o da camada). Caminhos relativos à raiz do
# repositório, a pasta do primeiro arquivo de compose.
services:
  api:
    volumes:
      - ./deploy/sources:/sources:ro
  worker:
    volumes:
      - ./deploy/sources:/sources:ro
```

Suba com um nome de projeto próprio (`-p knobridge-eval`), para não tocar nos volumes do ambiente de desenvolvimento nem nos do E2E, e com outras portas se o ambiente de desenvolvimento estiver no ar (veja [subir-ambiente.md](subir-ambiente.md#rodar-o-e2e-contra-a-stack); troque também `COMPOSE_SUBNET` e `FRONTEND_IPV4`, este no `.250` da nova sub-rede):

```bash
export API_PORT=38000 FRONTEND_PORT=35173 POSTGRES_PORT=35432 TEMPORAL_PORT=37233 \
  TEMPORAL_UI_PORT=38080 MAILPIT_SMTP_PORT=31025 MAILPIT_UI_PORT=38025 \
  MINIO_API_PORT=39000 MINIO_CONSOLE_PORT=39001 WEBHOOK_SINK_PORT=38090 \
  COMPOSE_SUBNET=10.213.92.0/24 FRONTEND_IPV4=10.213.92.250
docker compose -p knobridge-eval -f docker-compose.yml -f docker-compose.e2e.yml \
  -f ../kb-eval/eval-sources.yml up -d --build --wait
docker compose -p knobridge-eval exec worker ls /sources/eval
# codigo  interno  manual
```

### 3. Criar o usuário e o workspace da avaliação

Na stack nova, abra o painel (<http://localhost:35173> no exemplo acima) e faça a configuração inicial ([primeiro-acesso.md](primeiro-acesso.md)): ela cria o superadmin e o primeiro workspace, já como owner. O id do workspace está no endereço, depois de `/w/`. Guarde o e-mail e o id; a senha vai por variável de ambiente.

O roteiro cria o resto: credencial, coleção, as cinco fontes, o produto, a chave de API e a configuração dos níveis.

### 4. Rodar com o provedor `fake`

O roteiro fala direto com a API (`--base-url`, a porta `API_PORT`). A senha vai em `KNOBRIDGE_EVAL_PASSWORD`; o roteiro recusa senhas e chaves na linha de comando:

```bash
cd scripts
export KNOBRIDGE_EVAL_PASSWORD='<senha do superadmin>'
uv run python -m eval run --base-url http://localhost:38000 \
  --email <e-mail do superadmin> --workspace-id <id do workspace> \
  --label fake --cleanup --out ../../kb-eval/fake
```

- O roteiro mostra o andamento no terminal: a preparação, a espera da indexação (até `--index-timeout`, padrão 600 s), cada pergunta e o encerramento.
- `--out` precisa ficar **fora do repositório** (o roteiro recusa um caminho dentro dele): o relatório traz as respostas inteiras.
- `--cleanup` exclui no fim o que o roteiro criou. Sem ele, tudo fica no workspace para você abrir no painel (as conversas aparecem em **Conversas**, no canal API); rodar de novo exige outro `--label`, porque os nomes `eval-<rótulo>-…` são únicos.
- Códigos de saída: 0 terminou (mesmo com respostas erradas), 1 falhou a preparação ou a indexação (inclusive a stack fora do ar), 2 entrada inválida.

Opções mais usadas (todas em `uv run python -m eval run --help` e em [avaliacao.md](../specs/avaliacao.md#linha-de-comando)):

| Opção | Para quê |
|---|---|
| `--max-steps <nível>=<n>` | Máximo de buscas de um nível nesta execução (1 a 6). `1` nos três dá a linha de base sem busca em etapas. Repita para cada nível. |
| `--rerank on` ou `off` | A opção **Reordenar trechos** do produto. |
| `--min-similarity <0 a 1>` | Fixa o limiar do produto; sem a opção, vale o padrão do modelo de embedding. |
| `--levels end_user,support` | Só as perguntas destes níveis. |
| `--repeat <1 a 5>` | Repete cada pergunta, para ver a variação do modelo. |
| `--questions <arquivo>` | Outro arquivo de perguntas no mesmo formato (por exemplo, perguntas com dados reais, fora do repositório, com `--redact-answers`). |

### 5. Ler o relatório

O `run` grava `report.json` (completo, para a comparação e para scripts) e `report.md` (para ler e colar num relatório de ensaio) na pasta de `--out`. O `report.md` tem:

1. **Cabeçalho**: rótulo, datas, arquivo de perguntas (com o `sha256`), modelo de embedding e limiar em uso, reranker, e o modelo e o máximo de buscas de cada nível.
2. **Resumo** por nível e total: respostas, corretas, "não sei", erradas, vazamentos, erros, acerto, recall de fonte, média de buscas, custo total e médio, latência p50 e p95.
3. A mesma tabela só para as **perguntas que pedem mais de uma busca** (`needs_steps`), escritas com palavras de negócio para uma resposta que está num documento com o termo técnico.
4. **Índice**: fontes, documentos, trechos e os arquivos que dominam o índice (o corpus traz `gerado/**` de propósito, então a fonte `eval-<rótulo>-codigo` deve mostrá-lo).
5. **Respostas**: uma linha por resposta, com o veredito, as buscas, o custo, a latência e as citações.
6. **Respostas não corretas**, com a pergunta e o começo da resposta.

Como ler os vereditos:

| Veredito | Significa | O que olhar |
|---|---|---|
| correta | Citou a fonte esperada e trouxe os termos obrigatórios; numa pergunta sem resposta no nível, disse que não sabe. | — |
| não sei | Disse que não sabe, mas o corpus tinha a resposta no nível. | Recall da busca: rode a pergunta em **Testar busca** na coleção; experimente mais buscas no nível ou o reranker. |
| errada | Citou outra fonte, faltou um termo obrigatório, trouxe um termo proibido, ou respondeu uma pergunta sem resposta (alucinação). | As citações e o texto em "Respostas não corretas". |
| vazamento | Citou uma fonte acima do nível da pergunta. | **Grave**: o filtro de nível no SQL não deveria permitir. Abra um chamado com o relatório. |
| erro | A chamada falhou ou a resposta terminou em `failed`. | O código de erro na linha. |

O julgamento é mecânico: mede se a resposta citou a fonte certa e contém os termos-chave, não se está bem escrita. Leia uma amostra das respostas antes de concluir.

Com o `fake`, espere: todas as fontes indexadas, o aviso `gerado/**` na fonte de código, **nenhum vazamento** e nenhum erro. O acerto e as buscas não significam nada.

### 6. Comparar duas execuções

Rode a mesma avaliação com outra configuração e outro `--label` (por exemplo, `--max-steps end_user=1 --max-steps support=1 --max-steps product_dev=1 --rerank off --label base` e depois sem essas opções, `--label etapas`) e compare:

```bash
cd scripts
uv run python -m eval compare ../../kb-eval/base/report.json ../../kb-eval/etapas/report.json \
  --out ../../kb-eval/base-x-etapas.md
```

O Markdown traz as configurações que diferem, o resumo por nível com as duas colunas e a diferença (acerto, recall de fonte, "não sei", vazamentos, buscas, custo médio e latência p50) e as perguntas que mudaram de veredito, com as buscas e o custo nas duas execuções. Relatórios de arquivos de perguntas diferentes recebem um aviso no topo, e só as perguntas em comum entram.

### 7. Derrubar a stack

```bash
docker compose -p knobridge-eval -f docker-compose.yml -f docker-compose.e2e.yml \
  -f ../kb-eval/eval-sources.yml down -v
```

O corpus copiado continua em `deploy/sources/eval/` (ignorado pelo Git); apague a pasta se não for rodar de novo.

## Medir com um provedor real

Para medir qualidade, use embeddings e modelos de verdade e, de preferência, o reranker de verdade:

1. Suba a stack isolada **sem** a camada de E2E (o compose de desenvolvimento já monta `deploy/sources/` em `/sources` e sobe o reranker; a primeira subida baixa o modelo, [subir-ambiente.md](subir-ambiente.md#reranker)), com o mesmo `-p knobridge-eval` e as portas trocadas:

   ```bash
   docker compose -p knobridge-eval up -d --build --wait
   ```

2. Ponha as chaves em variáveis de ambiente (nunca na linha de comando): `KNOBRIDGE_EVAL_CHAT_KEY` para o provedor dos níveis e, quando o provedor de embedding for outro, `KNOBRIDGE_EVAL_EMBEDDING_KEY`.
3. Rode com os provedores e os modelos de cada nível:

   ```bash
   cd scripts
   export KNOBRIDGE_EVAL_PASSWORD='<senha>' KNOBRIDGE_EVAL_CHAT_KEY='<chave do OpenRouter>'
   uv run python -m eval run --base-url http://localhost:38000 \
     --email <e-mail> --workspace-id <id> \
     --chat-provider openrouter --embedding-provider openrouter \
     --embedding-model openai/text-embedding-3-small \
     --model end_user=openai/gpt-4.1-mini --model support=openai/gpt-4.1-mini \
     --model product_dev=openai/gpt-4.1 \
     --label real-etapas --cleanup --out ../../kb-eval/real-etapas
   ```

O custo aparece no resumo (modelos sem preço conhecido contam como `unpriced`; acrescente o preço em `KNOBRIDGE_CHAT_PRICES`, [uso-e-custos.md](../specs/uso-e-custos.md#preços-do-chat)). A Anthropic não tem embeddings: com `--chat-provider anthropic`, use outro `--embedding-provider`.

## Como verificar

- O `run` termina com "relatório em …: N de 30 respostas corretas" e código de saída 0.
- No `report.md`, a coluna **Vazamentos** está zerada em todos os níveis e a tabela **Índice** lista as cinco fontes com documentos e trechos.
- Sem `--cleanup`, o painel mostra a coleção `eval-<rótulo>`, as fontes e as conversas do canal API.

## Como desfazer

- O encerramento do `run` sempre revoga a chave e restaura os níveis como estavam (credencial, modelo, temperatura e máximo de buscas), mesmo depois de erro ou `Ctrl+C`. Com `--cleanup`, também exclui produto, fontes, coleção e credenciais criadas.
- Sem `--cleanup`, exclua no painel o produto, as fontes, a coleção e as credenciais `eval-<rótulo>`, nessa ordem.
- `down -v` no projeto `knobridge-eval` apaga a stack inteira.

## Problemas comuns

- **`erro: chaves e senhas não vão na linha de comando`** (código 2): uma opção ou valor parece segredo (`--…key…`, `--password`, `sk-…`, `kbk_…`). Use as variáveis `KNOBRIDGE_EVAL_*`.
- **`… fica dentro do repositório; grave o relatório fora dele`** (código 2): escolha um `--out` fora do clone, como `../../kb-eval/<rótulo>`.
- **A indexação falha com caminho inexistente** (código 1): a stack não vê `/sources/eval`. Rode o `copy-corpus`, confira `docker compose -p knobridge-eval exec worker ls /sources/eval` e, com a camada de E2E, o terceiro arquivo de compose do passo 2.
- **Nome já em uso** (`source_name_taken`, `collection_name_taken`): uma execução sem `--cleanup` deixou os recursos. Use outro `--label` ou exclua os antigos.
- **A preparação para com 401 ou 403** (código 1): senha errada em `KNOBRIDGE_EVAL_PASSWORD` (401), ou o usuário não é owner nem admin do workspace informado, ou o id é de outro workspace (403).
- **A indexação passa do tempo** (código 1): com embeddings reais e limite de uso do provedor, aumente `--index-timeout`.
- **Com o `fake`, o acerto é baixo e as buscas variam**: esperado. O `fake` só prova o caminho; meça com um provedor real.

## Referências

- [avaliacao.md](../specs/avaliacao.md): o contrato do conjunto e do roteiro.
- [scripts/eval/AGENTS.md](../../scripts/eval/AGENTS.md): o código e os testes.
- [chat.md](../specs/chat.md#busca-em-etapas) (busca em etapas) e [indexacao.md](../specs/indexacao.md#reranker) (reranker e limiar por modelo).
- uv: <https://docs.astral.sh/uv/>
- Docker Compose com vários arquivos (caminhos relativos ao primeiro arquivo): <https://docs.docker.com/compose/how-tos/multiple-compose-files/merge/>
