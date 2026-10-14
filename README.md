# KnoBridge

Plataforma open source (Apache 2.0) que conecta repositórios de código, sistemas de chamados e documentações, transforma tudo em índices para RAG e responde em linguagem natural, sempre citando a fonte. Sem fonte, o assistente diz que não sabe e oferece abrir um chamado.

> **Status**: em desenvolvimento; Fase 0 do roadmap concluída. Já funcionam painel, workspaces, indexação de pastas, repositórios Git, código (via runner), chamados e cards de desenvolvimento, produtos com três níveis de resposta (usuário final, suporte, desenvolvimento e produto), chat com citações, uso e custos, API pública (REST e compatível com OpenAI), servidor MCP para assistentes de código (Claude Code, Cursor, Codex) e widget embutível para sites e sistemas; ainda não há canvas de pipelines nem Slack e Google Chat. O que mudou está no [CHANGELOG.md](CHANGELOG.md).

## Requisitos

- Docker com Compose v2 (`docker compose version` responde 2.x) e cerca de 4 GB de RAM livres.
- Uma chave de API do [OpenRouter](https://openrouter.ai/) (cobre embeddings e chat), ou da OpenAI.

## Início rápido

Da instância vazia a uma resposta com citação sobre os seus próprios documentos. Todos os comandos rodam na raiz do repositório.

1. **Ponha alguns documentos na pasta de fontes.** Copie uns poucos `.md`, `.pdf` ou `.docx` que você conhece para uma subpasta de `deploy/sources/` (ignorada pelo Git):

   ```bash
   mkdir -p deploy/sources/manual && cp ~/Documentos/*.md deploy/sources/manual/
   ```

   No Windows, crie a pasta `deploy\sources\manual` e copie os arquivos pelo Explorador. Para usar outra pasta do host, rode `cp .env.example .env` e aponte `KNOBRIDGE_SOURCES_DIR` para ela. Essa pasta aparece **somente leitura** em `/sources` dentro dos contêineres.

2. **Suba a stack.**

   ```bash
   docker compose up -d --build --wait
   ```

   A primeira vez constrói as imagens e leva alguns minutos. O comando volta quando tudo está saudável; confira com `docker compose ps -a` (`migrate` aparece `exited (0)`).

3. **Crie o superadmin e o workspace.** Abra o painel em <http://localhost:5173>. Na tela **Configuração inicial**, informe nome, e-mail (fictício serve, ex.: `voce@example.test`), senha de 12 caracteres ou mais e o **Nome do workspace**, e clique em **Criar conta e entrar**. O painel abre o **Início** do workspace, com a lista **Primeiros passos** (os passos abaixo), e o topo deve mostrar **API: disponível**.

4. **Cadastre o provedor.** Em **Provedores** > **Novo provedor**: **Tipo** `OpenRouter`, **Nome** `OpenRouter`, **Chave de API** a sua chave (deixe **URL base (opcional)** em branco). Clique em **Salvar** e, na linha do provedor, em **Testar conexão**: deve aparecer "Conexão com OpenRouter funcionando."

   Com a OpenAI direta, use **Tipo** `OpenAI`; nos próximos passos, os modelos ficam sem o prefixo `openai/`.

5. **Crie a coleção.** Em **Coleções** > **Nova coleção**: **Nome** (ex.: `Meus documentos`), **Credencial de embedding** o provedor do passo 4 e **Modelo de embedding** `openai/text-embedding-3-small`. Clique em **Salvar**.

6. **Cadastre e sincronize a fonte.** Em **Fontes** > **Nova fonte**: **Nome**, **Coleção** a do passo 5, **Tipo** `Pasta` e **Caminho da pasta** `/sources/manual` (o caminho de dentro do contêiner, nunca o do host nem a raiz `/sources`). Deixe **Ativa** marcada e clique em **Salvar**. Clique no nome da fonte e use **Testar conexão** ("A fonte ... está acessível.") e **Sincronizar agora**. Em **Execuções**, a linha passa de **Na fila** a **Em execução** e termina **Concluída**, com documentos novos e trechos maiores que zero.

7. **Configure os níveis de resposta.** Cada pergunta é respondida num nível (**Usuário final**, **Suporte** ou **Desenvolvimento e produto**), e é o nível que tem o modelo. Em **Configurações** > **Níveis de resposta**, em cada um dos três cartões, escolha a **Credencial** do passo 4, informe o **Modelo** `openai/gpt-4.1-mini` (qualquer modelo de chat do OpenRouter serve, com o prefixo do fornecedor) e clique em **Salvar nível**.

8. **Crie o produto.** O produto é o sistema sobre o qual se pergunta. Em **Produtos** > **Novo produto**: **Nome** (ex.: `Meu sistema`) e, em **Coleções**, marque a coleção do passo 5. A **Similaridade mínima** padrão (0,35) é calibrada para o embedding da OpenAI; deixe como está. Clique em **Salvar**.

9. **Pergunte.** Em **Chat**, escolha o **Produto** e o **Nível de resposta** (o seu máximo vem marcado), escreva uma pergunta sobre os seus documentos e clique em **Enviar**. A resposta chega em streaming com marcadores `[1]`, `[2]`... e, abaixo dela, as **Fontes**: clique numa para ver o trecho e o arquivo. Uma pergunta sem relação com os documentos volta com "Respondida sem fonte: o assistente ofereceu abrir chamado." Arquivos de código numa pasta só aparecem em **Desenvolvimento e produto**: o usuário final nunca recebe código.

Se o chat responder "sem fonte" para uma pergunta que deveria ter resposta, abra a coleção e use **Testar busca** para ver o que a busca encontra; detalhes em [indexar-uma-fonte.md](docs/guias/indexar-uma-fonte.md#problemas-comuns).

## Próximos passos

- **Indexar um repositório Git** (clone em `/sources` ou URL https pública): [indexar-uma-fonte.md](docs/guias/indexar-uma-fonte.md#4-cadastrar-a-fonte).
- **Mapear código com o runner** (Claude Code ou Codex somente leitura na sua máquina, gerando regras de negócio com evidência): [mapear-codigo-com-runner.md](docs/guias/mapear-codigo-com-runner.md).
- **Produtos e níveis de resposta** (o nível máximo de cada membro, o nível mínimo das fontes, um modelo por nível): [produtos-e-niveis.md](docs/guias/produtos-e-niveis.md).
- **Receber chamados por API** (token de envio ou upload de JSON/JSONL, com anonimização): [receber-chamados-por-api.md](docs/guias/receber-chamados-por-api.md).
- **Receber cards de desenvolvimento** (Jira, Azure DevOps, GitHub Issues…) pelo mesmo caminho, citados para desenvolvimento e produto: [receber-cards-por-api.md](docs/guias/receber-cards-por-api.md).
- **"Abrir chamado" no seu sistema** a partir de uma resposta sem fonte, por webhook assinado: [receber-chamados-por-api.md](docs/guias/receber-chamados-por-api.md#9-receber-abrir-chamado-do-chat).
- **Chamar os produtos de outro sistema** com uma chave de API (com nível máximo), pela REST ou pelo SDK oficial da OpenAI (`model` = `produto:nível`), com as citações na resposta: [usar-a-api.md](docs/guias/usar-a-api.md).
- **Usar os produtos no Claude Code, no Cursor ou no Codex** pelo servidor MCP (`/v1/mcp`), com a mesma chave de API: busca com citações sem custo de LLM, resposta pronta e abrir chamado: [conectar-pelo-mcp.md](docs/guias/conectar-pelo-mcp.md).
- **Pôr o chat no seu site ou sistema** com o widget (uma linha de `<script>` e um elemento, sempre no nível Usuário final, com avaliação, abrir chamado e identidade assinada opcional): [embutir-o-widget.md](docs/guias/embutir-o-widget.md).
- Convidar pessoas, papéis, painel da instância, uso e custos e outros fluxos de conta: [primeiro-acesso.md](docs/guias/primeiro-acesso.md).

## Parar e limpar

```bash
docker compose stop      # para os contêineres; `docker compose up -d --wait` retoma
docker compose down      # remove os contêineres, mantém os dados (volumes)
docker compose down -v   # apaga também banco, MinIO e clones; deploy/sources/ não é tocada
```

Depois de `down -v`, a próxima subida volta à **Configuração inicial**.

## Problemas comuns

- **Porta já em uso**: troque a porta no `.env` (ex.: `FRONTEND_PORT`, `MAILPIT_UI_PORT`, `API_PORT`) e suba de novo.
- **Fonte falha com "fora da pasta liberada" ou "Não foi possível ler a fonte"**: use `/sources/<subpasta>`, confira com `docker compose exec worker ls /sources` e, se mudou `KNOBRIDGE_SOURCES_DIR`, recrie com `docker compose up -d --wait`. No Windows, a pasta precisa estar num disco compartilhado com o Docker Desktop.
- **E-mail não aparece no Mailpit**: confira `docker compose ps mailpit` e procure `email_delivery_failed` em `docker compose logs api`.
- **Painel mostra "API: indisponível"**: confira se a `api` está `healthy` e se `curl http://localhost:5173/v1/health/ready` responde 200.

Portas, serviços e mais casos em [docs/guias/subir-ambiente.md](docs/guias/subir-ambiente.md#problemas-comuns).

## Desenvolver

Antes de mudar qualquer coisa (humano ou agente de IA), leia [AGENTS.md](AGENTS.md). Cada pacote tem gate de 95% de cobertura de linhas e branches; no Windows, exporte `PYTHONUTF8=1`.

- `backend/`: `uv sync && uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest` ([README](backend/README.md)).
- `frontend/`: `pnpm install --frozen-lockfile && pnpm lint && pnpm format:check && pnpm typecheck && pnpm test && pnpm build` ([README](frontend/README.md)).
- `widget/`: `pnpm install --frozen-lockfile && pnpm lint && pnpm format:check && pnpm typecheck && pnpm test && pnpm build` ([AGENTS.md](widget/AGENTS.md)).
- `runner/`: `uv sync && uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest` ([README](runner/README.md)).
- `scripts/`: `uv sync && uv run ruff check . && uv run pyright && uv run pytest` ([AGENTS.md](scripts/AGENTS.md)).
- Hooks de pre-commit, da raiz: `uvx pre-commit run --all-files`.

A CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) roda tudo isso, mais o E2E da stack ([subir-ambiente.md](docs/guias/subir-ambiente.md#rodar-o-e2e-contra-a-stack)), varredura de segredos e validação do compose.

## Onde ler mais

- [docs/01-visao-do-projeto.md](docs/01-visao-do-projeto.md): visão, arquitetura, stack, decisões e roadmap.
- [docs/guias/](docs/guias/): guias de uso e operação.
- [docs/specs/](docs/specs/): contratos (autenticação, chat, produtos e níveis, API pública, MCP, widget, uso e custos, conectores, indexação, runner, harness, chamados, cards, modelo de dados, OpenAPI).
- [docs/adr/](docs/adr/): decisões de arquitetura.
- [docs/planos/](docs/planos/): planos de execução, com andamento e decisões.
- [CHANGELOG.md](CHANGELOG.md): o que mudou.
