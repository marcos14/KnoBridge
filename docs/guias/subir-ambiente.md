# Subir o ambiente de desenvolvimento

> Rascunho v0.3 · 2026-10-17 · Em uso
>
> **Mudanças da v0.3** (plano 0011): o serviço `reranker` (primeira subida, memória, `--max-batch-tokens`, `start_period` e como subir sem ele), as variáveis do reranker e do limiar por modelo, o endereço do painel no `.250` da sub-rede, o reranker falso e o E2E da qualidade da resposta na camada de E2E.
>
> **Mudanças da v0.2**: o ambiente já traz a plataforma navegável do plano 0002 (autenticação, workspaces, painel admin e chat); o primeiro uso está em [primeiro-acesso.md](primeiro-acesso.md).

Como subir o KnoBridge completo na sua máquina com Docker Compose: banco, Temporal, armazenamento de objetos, servidor de e-mail de desenvolvimento, reranker, migrações, API, worker e painel. Com o ambiente saudável, siga [primeiro-acesso.md](primeiro-acesso.md) para criar o superadmin, o primeiro workspace, um provedor de LLM, os níveis de resposta e um produto, e conversar com ele. Para o chat responder com citações, indexe uma fonte ([indexar-uma-fonte.md](indexar-uma-fonte.md)).

## Pré-requisitos

- Docker com Compose v2 (`docker compose version` deve responder 2.x). No Windows e no macOS, Docker Desktop com engine Linux.
- Cerca de 8 GB de RAM livres para os contêineres (até 4 GB só para o reranker, cerca de 3,2 GB depois de subir) e 6 GB de disco para as imagens e o modelo do reranker (cerca de 2,3 GB, baixado na primeira subida). Com menos memória, suba sem o reranker ([abaixo](#reranker)).
- As portas da tabela abaixo livres no `127.0.0.1` (ou troque-as no `.env`).

Não é preciso ter Python, `uv`, Node nem `pnpm` instalados para este guia: as imagens do backend e do frontend são construídas dentro do Docker.

## Passos

Todos os comandos rodam a partir da raiz do repositório.

1. Crie o arquivo de variáveis (opcional: sem ele, valem os mesmos defaults de desenvolvimento):

   ```bash
   cp .env.example .env
   ```

   As credenciais do exemplo são **só para desenvolvimento**. O `.env` (na raiz do repositório) é ignorado pelo git; nunca o commite.

2. Construa as imagens e suba tudo:

   ```bash
   docker compose up --build
   ```

   Para rodar em segundo plano e só devolver o terminal quando todos os serviços estiverem saudáveis:

   ```bash
   docker compose up -d --build --wait
   ```

   Ordem de subida: `postgres` e `mailpit` saudáveis → `temporal` e `migrate` → `api` (depois que `migrate` termina com sucesso) e `worker` (depois que `migrate` termina e o Temporal fica saudável), ambos só com o `mailpit` saudável → `frontend` (depois que a `api` fica saudável). O `reranker` sobe em paralelo e ninguém depende dele, mas o `--wait` espera por ele: na **primeira subida**, que baixa o modelo, o comando pode levar vários minutos (o healthcheck dá até 15 minutos, `start_period`); nas seguintes, o modelo já está no volume e ele só carrega os pesos.

## Serviços e portas

| Serviço | Imagem | Porta no host | Variável da porta | Para quê |
|---|---|---|---|---|
| `postgres` | `pgvector/pgvector:pg17` | 5432 | `POSTGRES_PORT` | Banco da aplicação (`knobridge`) e do Temporal (`temporal`, `temporal_visibility`) |
| `temporal` | `temporalio/auto-setup:1.29.7` | 7233 | `TEMPORAL_PORT` | Servidor Temporal (gRPC) |
| `temporal-ui` | `temporalio/ui:2.55.0` | 8080 | `TEMPORAL_UI_PORT` | Interface web do Temporal |
| `minio` | `pgsty/minio:RELEASE.2026-08-04T00-00-00Z` | 9000 (API S3), 9001 (console) | `MINIO_API_PORT`, `MINIO_CONSOLE_PORT` | Armazenamento de objetos compatível com S3 |
| `mailpit` | `axllent/mailpit:v1.31.4` | 1025 (SMTP), 8025 (interface web) | `MAILPIT_SMTP_PORT`, `MAILPIT_UI_PORT` | Servidor SMTP de desenvolvimento: recebe os e-mails da API e do worker e os mostra na interface, sem entregar a ninguém |
| `reranker` | `ghcr.io/huggingface/text-embeddings-inference:cpu-1.9.4` (`RERANKER_IMAGE`) | — (só na rede do compose) | — | Reranker `BAAI/bge-reranker-v2-m3` (Text Embeddings Inference em CPU) que reordena os melhores trechos de cada busca ([indexacao.md](../specs/indexacao.md#reranker)). Memória, primeira subida e como subir sem ele em [Reranker](#reranker) |
| `migrate` | backend (local) | — | — | Roda `alembic upgrade head` uma vez e termina |
| `api` | backend (local) | 8000 | `API_PORT` | API REST (`knobridge-api`) |
| `worker` | backend (local) | — | — | Worker Temporal (`knobridge-worker`), fila `knobridge` |
| `frontend` | frontend (local) | 5173 | `FRONTEND_PORT` | Painel admin (nginx), com proxy de `/v1/` para a `api` |

Todas as portas são publicadas só em `127.0.0.1` (variável `BIND_ADDRESS`).

## Como verificar

1. Estado dos serviços: todos `running (healthy)`, exceto `migrate`, que deve aparecer `exited (0)`.

   ```bash
   docker compose ps -a
   ```

2. API pronta (inclui o teste de conexão com o banco):

   ```bash
   curl http://localhost:8000/v1/health/ready
   # {"status":"ok","checks":{"database":"ok"}}
   ```

3. Painel: abra <http://localhost:5173>. O indicador no topo deve mostrar **"API: disponível"**. A mesma checagem pelo proxy do painel:

   ```bash
   curl http://localhost:5173/v1/health/ready
   ```

4. Worker conectado ao Temporal: o log deve ter o evento `worker_started`, e a fila `knobridge` deve listar pollers.

   ```bash
   docker compose logs worker
   docker compose exec temporal \
     temporal task-queue describe --address temporal:7233 --task-queue knobridge
   ```

5. Temporal UI: abra <http://localhost:8080> e confira o namespace `default`.

6. Console do MinIO: abra <http://localhost:9001> e entre com `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` (padrão de dev: `knobridge` / `knobridge-dev`).

7. E-mails: abra <http://localhost:8025> (Mailpit). Todo e-mail transacional enviado pela API ou pelo worker (redefinição de senha, verificação de e-mail, convite) aparece ali, e nenhum sai para caixas reais. Os links apontam para `KNOBRIDGE_PUBLIC_BASE_URL` (padrão `http://localhost:5173`, o painel). Para conferir só o servidor:

   ```bash
   curl http://localhost:8025/api/v1/info
   ```

8. Reranker: o serviço deve estar `healthy` (na primeira subida, depois do download do modelo). Ele não publica porta no host; confira de dentro do contêiner:

   ```bash
   docker compose ps reranker
   docker compose exec reranker curl -fsS http://127.0.0.1:80/health
   ```

## Configuração da API e do worker

O compose passa para `api`, `worker` e `migrate` as variáveis abaixo, com default de desenvolvimento; as configuráveis estão em `.env.example`:

| Variável | Padrão no compose | Para quê |
|---|---|---|
| `KNOBRIDGE_SECRET_KEY` | `dev-only-insecure-secret-key-change-me` | Assina os tokens CSRF e é a raiz das chaves que cifram as chaves de API dos provedores ([ADR 0003](../adr/0003-segredos-cifrados.md)); trocá-lo exige recadastrar essas chaves. **Valor público, só para desenvolvimento**: fora da sua máquina, gere um com `python -c "import secrets; print(secrets.token_urlsafe(48))"` e ponha no `.env` |
| `KNOBRIDGE_PUBLIC_BASE_URL` | `http://localhost:${FRONTEND_PORT}` | Endereço do painel, como o navegador o vê, usado nos links dos e-mails |
| `KNOBRIDGE_SMTP_FROM` | `KnoBridge <no-reply@knobridge.local>` | Remetente dos e-mails |
| `KNOBRIDGE_SMTP_HOST` / `KNOBRIDGE_SMTP_PORT` | `mailpit` / `1025` | Fixos: neste ambiente o SMTP é sempre o Mailpit |
| `KNOBRIDGE_ENV` | `local` | Ambiente do backend. Qualquer valor diferente de `production` aceita o provedor de LLM `fake` (sem rede, para testes) |
| `KNOBRIDGE_COOKIE_SECURE` | `false` | **Só em desenvolvimento**: o painel aqui é HTTP puro, então os cookies não levam `Secure`. Com HTTPS, use `true` (o padrão da aplicação) |
| `KNOBRIDGE_FORWARDED_ALLOW_IPS` (só `api`) | `${FRONTEND_IPV4}` (`10.213.57.250`) | Proxies cujo `X-Forwarded-For` a API aceita. O nginx do painel repassa `/v1` para a `api`; confiando só nele, o IP do cliente (usado na limitação de tentativas de login) é o do navegador, e não o do proxy |
| `KNOBRIDGE_LOCAL_SOURCES_ROOT` | `/sources` | Fixo: fontes de pasta e repositórios Git locais precisam estar abaixo de `/sources`, onde `api` e `worker` montam a pasta do host (abaixo) |
| `KNOBRIDGE_GIT_WORKDIR` | `/var/lib/knobridge/git` | Fixo: onde o `worker` guarda os clones parciais dos repositórios cadastrados por URL https (volume `source-clones`) |
| `KNOBRIDGE_CHAT_PRICES` | `{}` | Preços de chat (US$ por milhão de tokens, entrada e saída) acrescentados à tabela embutida, para o custo estimado de cada resposta em **Uso e custos** ([uso-e-custos.md](../specs/uso-e-custos.md#preços-do-chat)). JSON entre aspas simples no `.env`; JSON inválido impede a subida |
| `KNOBRIDGE_MIN_SIMILARITY_DEFAULTS` | `{}` | Similaridade mínima padrão por modelo de embedding, por cima da tabela embutida (0,35 no `text-embedding-3-small`, 0,60 no `gemini-embedding-001`; [indexacao.md](../specs/indexacao.md#limiar-por-modelo-de-embedding)). Vale para os produtos com a similaridade mínima em branco. Ex.: `'{"gemini-embedding-001": 0.62}'`; JSON inválido ou valor fora de 0 a 1 impede a subida |
| `KNOBRIDGE_RERANKER_URL` (só `api`) | `http://reranker:80` | Onde a API chama o reranker. Vazia: a instância não tem reranker, as buscas ficam na ordem da busca híbrida e "Reordenar trechos" dos produtos não tem efeito |
| `KNOBRIDGE_RERANKER_TIMEOUT`, `_CANDIDATES`, `_MAX_CHARS`, `_MODEL` (só `api`) | `10`, `30`, `2000`, `BAAI/bge-reranker-v2-m3` | Segundos por chamada (passou disso, a busca fica na ordem original), trechos enviados por busca, caracteres por trecho e o nome que o painel mostra |

### Pasta de fontes

Fontes de pasta e repositórios Git locais são lidos de uma pasta do host, montada **somente leitura** em `/sources` na `api` (para o "Testar conexão") e no `worker` (que indexa). O padrão é `deploy/sources/`, vazia no repositório e ignorada pelo Git (só o `AGENTS.md` dela é versionado), para o que você colocar ali nunca ir parar num commit.

1. Ponha uma pasta ou um clone em `deploy/sources/` (ex.: `deploy/sources/manual/` ou `git clone ... deploy/sources/erp-core`), ou aponte `KNOBRIDGE_SOURCES_DIR` no `.env` da raiz para outra pasta do host (caminho absoluto, ou relativo à raiz do repositório).
2. Suba (ou recrie `api` e `worker` com `up -d`) e cadastre a fonte no painel com o caminho visto de dentro do contêiner: `/sources/manual`, `/sources/erp-core`. Cadastre a subpasta, não a raiz `/sources`.
3. Confira a montagem: `docker compose exec worker ls /sources`.

Repositórios por URL https não usam essa pasta: o `worker` clona no volume nomeado `source-clones`, que sobrevive a `down` e some com `down -v`. A imagem do backend traz o `git` e as dependências de parsing (MarkItDown com PDF/DOCX/XLSX/PPTX) e de tree-sitter; o build falha cedo se alguma delas não carregar.

A rede do compose tem sub-rede fixa (`COMPOSE_SUBNET`, padrão `10.213.57.0/24`) e o `frontend` tem endereço fixo nela (`FRONTEND_IPV4`, padrão `10.213.57.250`), para a `api` saber qual é o seu proxy. O endereço fica no alto da sub-rede porque o Docker distribui os dos outros contêineres a partir do `.2`; um `.env` antigo com `FRONTEND_IPV4` e `KNOBRIDGE_FORWARDED_ALLOW_IPS` em `.10` pode falhar com `Address already in use` ao criar o `frontend` (troque os dois para `.250`). Requisições direto na porta da `api` (`API_PORT`) não passam pelo nginx e contam o IP de quem conectou.

Rodando o backend fora do Docker (`uv run knobridge-api`), os defaults de `backend/.env.example` já apontam o SMTP para `localhost:1025`; suba só o Mailpit com `docker compose up -d --wait mailpit`.

### Reranker

O serviço `reranker` roda o Text Embeddings Inference (TEI) em CPU com o modelo `BAAI/bge-reranker-v2-m3`, que lê a pergunta e cada trecho juntos e reordena os 30 melhores candidatos da busca híbrida antes da resposta ([indexacao.md](../specs/indexacao.md#reranker)). Ele sobe sempre com o compose, em desenvolvimento e em produção ([ADR 0010](../adr/0010-busca-em-etapas-e-reranker.md)).

- **Primeira subida**: baixa o modelo, na revisão fixada em `RERANKER_MODEL_REVISION`, para o volume `reranker-models` (cerca de 2,3 GB). O TEI só abre a porta depois de carregar o modelo, por isso o healthcheck tem `start_period` de 15 minutos e o `up --wait` espera esse tempo. Acompanhe com `docker compose logs -f reranker`. As subidas seguintes reaproveitam o volume; `down -v` o apaga e a próxima subida baixa de novo.
- **Memória**: o contêiner tem limite de `RERANKER_MEMORY_LIMIT` (padrão `4g`) e usa cerca de 3,2 GB depois de subir. O comando fixa `--max-batch-tokens 2048`: sem ele, o TEI aquece no máximo do modelo (8.192 tokens), passa dos 4 GB e é morto por falta de memória em laço. Os trechos enviados têm até `KNOBRIDGE_RERANKER_MAX_CHARS` (2.000) caracteres, bem abaixo desse teto. No Docker Desktop, reserve memória para a VM de acordo (Settings > Resources).
- **ARM** (Apple Silicon, Linux ARM): use `RERANKER_IMAGE=ghcr.io/huggingface/text-embeddings-inference:cpu-arm64-1.9.4` no `.env`.
- **Sem reranker**: a `api` não depende dele. Enquanto ele não está saudável, ou se ele falhar, as buscas ficam na ordem da busca híbrida, sem erro na resposta (log `reranker_failed`). Para desligar de vez, deixe `KNOBRIDGE_RERANKER_URL=` vazia no `.env` e suba sem o serviço: `docker compose up -d --build --wait --scale reranker=0`. O painel desabilita "Reordenar trechos" nos produtos e o painel da instância mostra o reranker como desligado.
- **Onde ver**: o painel da instância (`/admin`) mostra o estado do reranker junto com API, banco, Temporal e worker; em **Coleções**, "Testar busca" compara a ordem dos trechos com e sem reranker.

## Derrubar e limpar

```bash
# Para e remove os contêineres, mantendo os dados (volumes).
docker compose down

# Remove também os volumes: banco, MinIO, clones de repositórios e o modelo do reranker
# (baixado de novo na próxima subida) voltam a ficar vazios
# (a pasta de fontes do host, deploy/sources/, não é tocada).
docker compose down -v
```

Depois de mudar código do backend ou do frontend, rode de novo com `--build` para reconstruir as imagens.

## Rodar o E2E contra a stack

Os testes Playwright de `frontend/e2e/stack/` exercitam o painel inteiro contra a API, o banco e o Mailpit reais. O primeiro cobre o primeiro acesso: a configuração inicial cria o superadmin e o workspace dele, sem convite, e abre o Início com o checklist. O segundo cobre a API pública: o superadmin entra num workspace pela administração, configura os níveis de resposta no provedor `fake`, indexa a pasta sintética, cria um produto e uma chave de API no painel (nível máximo Usuário final), e o SDK oficial `openai` para Node pergunta com `produto` e `produto:end_user`, com e sem streaming, recebe as citações no campo `knobridge` e um 403 `level_not_allowed` em `produto:support`; Uso e custos conta as respostas no canal `api`. O dos níveis faz a mesma pergunta num produto nos três níveis, com uma pasta de manual e código, uma pasta de consulta marcada como Suporte e um card enviado por `/v1/ingest/cards`: Usuário final cita só o manual, Suporte acrescenta a consulta e Desenvolvimento e produto, o código e o card. O fluxo da plataforma segue com o login do superadmin, a criação de workspace com convite do proprietário (o link é lido pela API HTTP do Mailpit), convite de um leitor, "esqueci minha senha" e redefinição, provedor `fake`, níveis de resposta e produto, chat do leitor (só Usuário final habilitado) com a resposta "sem fonte" e avaliação, a conversa na tela de conversas do proprietário, o tema que acompanha a conta e a indexação de ponta a ponta: coleção com embeddings do provedor `fake`, fonte de pasta em `/sources/knowledge`, teste de conexão, sincronização até a execução concluir, teste de busca, coleção ligada ao produto, resposta citando o arquivo e uma pergunta sem relação que cai em "sem fonte". Outro fluxo cobre o harness de código: o proprietário cria um runner no painel, o teste sobe o `knobridge-runner` de `runner/` na própria máquina (fora do compose) com o token, sobre um repositório Git sintético criado numa pasta temporária, e com o `claude` falso de `runner/tests/fakes/`; o runner fica online, a fonte runner recebe os módulos do relatório, um módulo roda, a regra aparece na aba Conhecimento, é aprovada, a sincronização do harness a indexa e o chat responde citando o item de conhecimento como revisado. Um terceiro cobre os chamados por API: o proprietário cria a fonte de chamados e o token de envio e confere a prévia da anonimização; o teste envia um lote pela API com o token (e o reenvia, sem mudança) e faz o upload de um JSONL; as sincronizações `ingest` indexam tudo e o chat cita o chamado; por fim o webhook do produto aponta para um sistema de chamados falso do compose, a entrega de teste passa e "Abrir chamado" numa resposta sem fonte volta com o número do chamado. O do MCP usa o SDK oficial `@modelcontextprotocol/sdk` em TypeScript com uma chave criada no painel: lista os produtos, busca trechos sem resposta de LLM (Uso e custos conta só a do `ask`), lê o documento citado, recebe a resposta de `ask` com citação, abre um chamado que chega ao sistema falso com o canal `mcp` e tem um nível acima do máximo da chave recusado. O do widget serve uma página de teste noutra porta da máquina (outra origem), com o `<script>` de `/widget/v1/knobridge-chat.js` da instância e o elemento: o visitante recebe a resposta citando o manual (nunca o código), avalia, abre um chamado com e-mail, encontra a conversa ao recarregar; a mesma página noutra origem é recusada, e uma identidade assinada com o segredo do painel aparece em Conversas. O da qualidade da resposta pergunta com os marcadores `[[buscar: …]]` que o provedor `fake` segue como roteiro de busca: o chat mostra "Buscando: <consulta>" enquanto a segunda busca roda e, no fim, "3 buscas" com as consultas; a mesma pergunta com a reordenação ligada e desligada no produto (e com e sem reranker em "Testar busca") muda a ordem das citações; e uma pasta com um relatório gerado de 211 trechos mostra o aviso de arquivo que domina o índice, que some depois de "Excluir" e de uma nova sincronização. O `pnpm e2e` comum não os roda.

A camada `docker-compose.e2e.yml` monta em `/sources`, no lugar de `deploy/sources/`, a pasta sintética `frontend/e2e/stack/fixtures/` (dois Markdown curtos em pt-BR e um arquivo TypeScript pequeno em `knowledge/`; em `levels/`, as pastas do E2E dos níveis de resposta, um manual com um arquivo de código e uma consulta de suporte; em `tickets/`, o JSONL que o teste envia por upload; em `quality/`, os documentos da busca em etapas e da reordenação e a pasta com o relatório gerado). Ela também troca o reranker de verdade pelo reranker falso (`scripts/fake_reranker.py`, sem download de modelo e com 256 MB de memória), que responde como o TEI e põe no topo o trecho com o marcador `[[rerank-top]]`. E sobe o `webhook-sink`, o sistema de chamados falso (`scripts/webhook_sink.py` numa imagem Python pequena), que confere a assinatura `KnoBridge-Signature`, responde `{ticket_id, url}` e guarda o canal e o solicitante de cada pedido. A `api` e o `worker` o alcançam em `http://webhook-sink:8090/hook`, liberado por `KNOBRIDGE_WEBHOOK_ALLOWED_HOSTS=webhook-sink`; o teste o lê pela porta `WEBHOOK_SINK_PORT` do host (padrão 8090).

Pré-requisitos, além do Docker: Node 24+ e `pnpm` em `frontend/`, com `pnpm install --frozen-lockfile` e `pnpm exec playwright install chromium` feitos uma vez; `git` e [uv](https://docs.astral.sh/uv/) no PATH, com `uv sync --frozen` feito uma vez em `runner/` (o teste do runner o roda com `uv run --frozen`). No Windows, onde o runner só acha `claude.exe` no PATH, o teste configura o `claude` falso como comando explícito, com o Python de `runner/.venv`.

1. Suba a stack com o arquivo de E2E por cima (projeto próprio, `knobridge-e2e`, separado dos volumes do ambiente de desenvolvimento):

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d --build --wait
   ```

2. Rode os testes, de `frontend/`:

   ```bash
   pnpm e2e:stack
   ```

3. Derrube e apague os volumes, para a próxima rodada começar do zero:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.e2e.yml down -v
   ```

Os testes usam só endereços sintéticos `@example.test`. Num banco limpo eles fazem a configuração inicial com o superadmin `admin@example.test`; num banco já usado entram com a mesma conta (`E2E_ADMIN_EMAIL` e `E2E_ADMIN_PASSWORD` trocam as credenciais) e criam o resto com um sufixo por rodada, então repetir sem `down -v` também funciona.

Com a stack em outras portas, informe as URLs: `E2E_BASE_URL` (painel, padrão `http://localhost:5173`) `E2E_MAILPIT_URL` (padrão `http://localhost:8025`) e `E2E_WEBHOOK_SINK_URL` (padrão `http://localhost:8090`). Para rodar ao mesmo tempo que o ambiente de desenvolvimento, troque as portas (`*_PORT`), a sub-rede (`COMPOSE_SUBNET`) e o endereço do painel (`FRONTEND_IPV4`), por exemplo:

```bash
export FRONTEND_PORT=15173 API_PORT=18000 POSTGRES_PORT=15432 TEMPORAL_PORT=17233 \
  TEMPORAL_UI_PORT=18080 MAILPIT_SMTP_PORT=11025 MAILPIT_UI_PORT=18025 \
  MINIO_API_PORT=19000 MINIO_CONSOLE_PORT=19001 WEBHOOK_SINK_PORT=18090 \
  COMPOSE_SUBNET=10.213.58.0/24 FRONTEND_IPV4=10.213.58.250
docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d --build --wait
(cd frontend && E2E_BASE_URL=http://localhost:15173 E2E_MAILPIT_URL=http://localhost:18025 \
  E2E_WEBHOOK_SINK_URL=http://localhost:18090 pnpm e2e:stack)
```

Na CI, o job `e2e-stack` de `.github/workflows/ci.yml` faz os mesmos três passos (mais o `uv sync --frozen` de `runner/`); quando falha, publica o relatório do Playwright (com o log do runner, `runner.log`, na pasta do teste) e os logs dos contêineres como artefato.

## Problemas comuns

- **Porta já em uso** (`bind: address already in use` ou `ports are not available`): troque a porta no `.env` (ex.: `MINIO_API_PORT=9010` e `MINIO_CONSOLE_PORT=9011`) e suba de novo. Para descobrir quem ocupa a porta: `netstat -ano | findstr :9000` (Windows) ou `lsof -i :9000` (Linux/macOS).
- **Mudei usuário, senha ou nome de banco no `.env` e nada mudou**: o script `deploy/postgres/init-databases.sh` só roda com o volume vazio. Rode `down -v` e suba de novo (apaga os dados locais).
- **`migrate` saiu com erro**: veja `docker compose logs migrate`. Em geral é banco inacessível ou credencial divergente entre `KNOBRIDGE_DB_*` e um volume antigo; `down -v` resolve em dev.
- **`temporal` demora a ficar saudável**: na primeira subida ele aplica os schemas e registra o namespace; o healthcheck só passa quando o namespace existe. Acompanhe com `docker compose logs -f temporal`.
- **E-mail não aparece no Mailpit**: confira se o `mailpit` está `healthy` (`docker compose ps mailpit`) e procure `email_delivery_failed` no log da `api` ou do `worker`. Fora do Docker, o backend precisa de `KNOBRIDGE_SMTP_HOST=localhost` e `KNOBRIDGE_SMTP_PORT` igual a `MAILPIT_SMTP_PORT`.
- **Painel mostra "API: indisponível"**: confira se a `api` está `healthy` e se `curl http://localhost:5173/v1/health/ready` responde 200. Se responder 502, o nginx não alcança a `api`.
- **`Pool overlaps with other one on this address space`** ao criar a rede: a sub-rede `COMPOSE_SUBNET` colide com outra rede Docker ou da sua máquina (ou com outra stack do KnoBridge rodando). Escolha outra no `.env` e ajuste `FRONTEND_IPV4` para um endereço dentro dela.
- **Fonte de pasta falha com caminho fora da raiz ou inexistente**: o caminho cadastrado é o de dentro do contêiner (`/sources/<pasta>`), não o do host. Confira com `docker compose exec api ls /sources`; se `KNOBRIDGE_SOURCES_DIR` mudou, recrie `api` e `worker` com `up -d`. No Windows, a pasta precisa estar num disco compartilhado com o Docker Desktop.
- **`up --wait` demora ou para no `reranker`**: na primeira subida ele baixa o modelo (cerca de 2,3 GB) antes de abrir a porta; acompanhe com `docker compose logs -f reranker`. Se o download falhar (rede, proxy), o healthcheck vence depois de 15 minutos: corrija a rede e rode `docker compose up -d --wait reranker`. Para trabalhar sem ele, veja [Reranker](#reranker).
- **`reranker` reinicia em laço** (`docker compose ps` com `Restarting` e `OOMKilled` em `docker inspect`): faltou memória. Confira se a VM do Docker Desktop tem memória para os 4 GB do contêiner, não tire o `--max-batch-tokens 2048` do comando e, se mudar o modelo, ajuste `RERANKER_MEMORY_LIMIT`.
- **`init-databases.sh` falha com `$'\r': command not found`**: o arquivo foi salvo com fim de linha CRLF. O `.gitattributes` força LF; rode `git add --renormalize .` ou salve o arquivo com LF e faça `down -v`.

## Referências

- Imagem do Postgres com pgvector: <https://hub.docker.com/r/pgvector/pgvector>
- Temporal auto-setup e variáveis (`DB`, `POSTGRES_SEEDS`, `SKIP_DB_CREATE`): <https://hub.docker.com/r/temporalio/auto-setup>
- Temporal UI: <https://hub.docker.com/r/temporalio/ui>
- Build comunitária do MinIO usada aqui (as imagens oficiais `minio/minio` deixaram de ser publicadas publicamente): <https://hub.docker.com/r/pgsty/minio>
- Mailpit (servidor SMTP de desenvolvimento): <https://mailpit.axllent.org/docs/>
- Text Embeddings Inference (imagem e opções do reranker, como `--max-batch-tokens`): <https://github.com/huggingface/text-embeddings-inference>
- Modelo `BAAI/bge-reranker-v2-m3`: <https://huggingface.co/BAAI/bge-reranker-v2-m3>
- Docker Compose (`depends_on`, `healthcheck`, `--wait`): <https://docs.docker.com/reference/compose-file/services/>
