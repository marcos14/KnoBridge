# frontend/e2e/stack/

**Função**: testes ponta a ponta do painel contra a stack inteira do compose (`deploy/docker-compose.yml` + `deploy/docker-compose.e2e.yml`): API, worker, Temporal, Postgres, Mailpit e o nginx do painel, todos reais. Configurados por `playwright.stack.config.ts` (projeto `stack`), fora do `pnpm e2e` comum.

**Entra aqui**:

- `platform.spec.ts`: o fluxo navegável (setup → login → workspace e convite do proprietário → aceite pelo link do e-mail → convite de leitor → esqueci a senha → redefinição → provedor `fake` e assistente → chat "sem fonte" com avaliação → a conversa vista pelo proprietário → tema que acompanha a conta → coleção, fonte de pasta em `/sources/knowledge`, teste de conexão, sincronização concluída, teste de busca → coleção ligada ao assistente → resposta citando o arquivo e pergunta sem relação "sem fonte").
- `runner.spec.ts`: o harness de código (plano 0004): runner criado no painel → `knobridge-runner` sobe no host com o token → online → fonte runner e teste de conexão → módulo do relatório → tarefa concluída → regra na aba Conhecimento, aprovada → as duas sincronizações do harness (resultado e aprovação) → chat citando o item de conhecimento como revisado.
- `tickets.spec.ts`: chamados por API (plano 0005): fonte de chamados e token de envio criados no painel → prévia da anonimização (marcadores, nada gravado) → lote enviado pela API com o token (`fetch` do Node) e reenviado sem mudança → upload do JSONL de `fixtures/tickets/` → sincronizações `ingest` até a caixa de entrada não ter pendências → coleção e webhook ligados ao assistente, segredo gerado e entregue ao receptor falso, entrega de teste aceita → chat citando o chamado (número, status e link) → "Abrir chamado" numa resposta sem fonte, confirmado, entregue com o número que o receptor devolveu.
- `webhookSink.ts`: fala com o receptor falso do compose (`webhook-sink`, `scripts/webhook_sink.py`): entrega o segredo `kbw_` (`PUT /secret`) e lê as entregas (`GET /deliveries`). A `api` e o `worker` o chamam por `http://webhook-sink:8090/hook`.
- `flows.ts`: passos compartilhados pelos specs (superadmin, workspace com convite, aceite, provedor `fake`, assistente, coleção, pergunta no chat).
- `localRunner.ts`: repositório Git sintético numa pasta temporária (código inline, dois arquivos em `src/`; a regra do `claude` falso cita `src/rules.py:1-2`, mudou um, confira o outro) e o processo do runner (`uv run --frozen knobridge-runner run` em `runner/`, configuração TOML e pasta de estado temporárias, log em `runner.log` na pasta do teste; parado e apagado no `afterAll`). O `claude` é o falso de `runner/tests/fakes/`: no PATH no Linux, comando explícito no Windows (o runner só resolve `claude.exe`).
- `mailpit.ts`: lê os e-mails pela API HTTP do Mailpit e devolve o link do token.
- `fixtures/knowledge/`: conhecimento sintético que a camada e2e do compose monta em `/sources` (dois Markdown curtos em pt-BR e um `.ts` pequeno; mudou o conteúdo, confira as palavras que o spec busca e pergunta).
- `fixtures/tickets/chamados.jsonl`: quatro chamados sintéticos para o upload, saída do gerador `scripts/synthetic_tickets` (semente 1, 4 chamados; o teste `repo` de `scripts/` confere). Para mudar, regenere em vez de editar.

**Não entra aqui**: testes que passam sem backend (ficam em `../`, com respostas sintéticas via `page.route`), testes de componente (Vitest, em `src/`), dados ou código reais, CLIs reais do Claude Code ou do Codex.

**Convenções locais**:

- Só dados sintéticos, e-mails `@example.test`. O superadmin é fixo (`E2E_ADMIN_EMAIL`/`E2E_ADMIN_PASSWORD`): banco limpo faz o setup, banco usado entra com ele. O resto ganha um sufixo por rodada, para repetir sem `down -v`. Cada spec cria o próprio workspace e não depende do outro.
- Uma pessoa por contexto do navegador (`browser.newContext()`), para cookies e `localStorage` separados.
- Sem `waitForTimeout`: espere pelo estado (`expect`, `expect.poll` ou `expect(...).toPass` com `timeout` explícito para e-mails, heartbeat e relatório do runner, tarefas e sincronizações). Depois de navegar pelo cliente, espere o título da nova página antes de preencher campos de mesmo nome.
- URLs só por ambiente: `E2E_BASE_URL` (painel; também é o servidor do runner e da API de ingestão), `E2E_MAILPIT_URL` e `E2E_WEBHOOK_SINK_URL` (receptor falso de webhook, padrão `http://localhost:8090`).
- Processo ou pasta temporária criados pelo teste são encerrados e apagados no `afterAll`.
- Sem retentativas; um worker, na ordem dos arquivos.

**Como testar**: com a stack no ar (`docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.e2e.yml up -d --build --wait`, da raiz) e `uv sync --frozen` feito em `runner/`, de `frontend/`: `pnpm e2e:stack`. Depois, `down -v`.

**Leia também**: [../AGENTS.md](../AGENTS.md); [docs/guias/subir-ambiente.md](../../../docs/guias/subir-ambiente.md) (seção do E2E contra a stack); [deploy/AGENTS.md](../../../deploy/AGENTS.md); [runner/tests/fakes/AGENTS.md](../../../runner/tests/fakes/AGENTS.md).
