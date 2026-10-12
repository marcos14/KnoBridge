---
id: 0005
titulo: Chamados por API — recebimento padronizado em fila, anonimização, citação no chat, abertura de chamado por webhook e comparação de embeddings
slug: chamados-por-api
solicitado_por: usuario
criado_em: 2026-10-12
atualizado_em: 2026-10-12
status: em_execucao
aprovado_em: 2026-10-12
aprovado_por: usuario
concluido_em: null
branch: plano/0005-chamados-por-api
fases:
  - id: F1
    titulo: Contrato e modelo de dados
    status: concluida
    subfases:
      - id: F1.1
        titulo: ADR 0006 e spec de chamados (formato, envio, fila, anonimização, Markdown, citação, webhook de saída)
        status: concluida
        agente: claude-code-worktree
        iniciada_em: 2026-10-12
        concluida_em: 2026-10-12
        commit: 619891f
      - id: F1.2
        titulo: Migração 0016 (fonte tickets, token de envio, caixa de entrada, webhook do assistente, solicitações de chamado) com RLS
        status: concluida
        agente: claude-code-worktree
        iniciada_em: 2026-10-12
        concluida_em: 2026-10-12
        commit: 69da51b
  - id: F2
    titulo: Servidor — recebimento e indexação
    status: concluida
    subfases:
      - id: F2.1
        titulo: Fonte tickets, token de envio e endpoint de lote para a caixa de entrada
        status: concluida
        agente: claude-code-worktree
        iniciada_em: 2026-10-12
        concluida_em: 2026-10-12
        commit: 520f19d
      - id: F2.2
        titulo: Anonimização determinística, Markdown do chamado e chunking
        status: concluida
        agente: null
        iniciada_em: null
        concluida_em: 2026-10-12
        commit: f8217a9
      - id: F2.3
        titulo: Conector interno tickets no workflow de ingestão e citação de chamado no chat
        status: concluida
        agente: claude-code-worktree
        iniciada_em: 2026-10-12
        concluida_em: 2026-10-12
        commit: 195ad2b
      - id: F2.4
        titulo: Upload JSON/JSONL pelo painel e prévia de anonimização
        status: concluida
        agente: claude-code-worktree
        iniciada_em: 2026-10-12
        concluida_em: 2026-10-12
        commit: 5c68746
  - id: F3
    titulo: Servidor — abrir chamado por webhook
    status: em_execucao
    subfases:
      - id: F3.1
        titulo: Webhook do assistente (URL, segredo cifrado, teste) e proteção contra SSRF
        status: em_execucao
        agente: claude-code-worktree
        iniciada_em: 2026-10-12
        concluida_em: null
        commit: null
      - id: F3.2
        titulo: Solicitação de chamado na conversa, resumo, entrega assinada com retentativas no Temporal
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
  - id: F4
    titulo: Painel
    status: pendente
    subfases:
      - id: F4.1
        titulo: Fonte de chamados (token, exemplo de envio, upload, prévia) e citação de chamado no chat
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F4.2
        titulo: Webhook no assistente e "Abrir chamado" no chat
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
  - id: F5
    titulo: Embedding do Gemini
    status: em_execucao
    subfases:
      - id: F5.1
        titulo: Embedding do Gemini pelo OpenRouter com 1536 dimensões
        status: em_execucao
        agente: claude-code-worktree
        iniciada_em: 2026-10-12
        concluida_em: null
        commit: null
  - id: F6
    titulo: Entrega e ensaios
    status: pendente
    subfases:
      - id: F6.1
        titulo: Gerador sintético de chamados, E2E da stack, guia, README, CHANGELOG e AGENTS raiz
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F6.2
        titulo: Ensaio sintético de chamados (anonimização, indexação, perguntas, abrir chamado)
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F6.3
        titulo: Comparação de embeddings OpenAI x Gemini em pt-BR
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
decisoes:
  - id: D1
    data: 2026-10-12
    por: usuario
    decisao: "Chamados entram por push num formato KnoBridge padronizado, numa fila, em vez de conectores que puxam de cada provedor"
    motivo: "não customizar um conector por sistema de chamados; quem integra converte para o formato uma vez (automação, webhook, iPaaS ou script)"
    alternativas: "conector por provedor (Zendesk, GLPI...); mapeamento configurável do webhook nativo"
    adr: docs/adr/0006-chamados-por-push.md
  - id: D2
    data: 2026-10-12
    por: usuario
    decisao: "Entrada pela API no formato KnoBridge e por upload de arquivo JSON ou JSONL no painel (mesma validação e mesma fila); sem CSV e sem mapeamento de webhook nativo"
    motivo: "a API cobre a integração contínua e o upload cobre a carga histórica sem código; JSON evita ambiguidade de mapeamento"
    alternativas: "CSV com colunas fixas; webhook nativo com mapeamento de campos"
    adr: null
  - id: D3
    data: 2026-10-12
    por: usuario
    decisao: "O formato padrão é só para chamados"
    motivo: "schema específico (conversa com papéis, solução, status) é mais rico para o chat; outros tipos podem usar o mesmo mecanismo depois"
    alternativas: "tipo documento genérico junto"
    adr: null
  - id: D4
    data: 2026-10-12
    por: usuario
    decisao: "Mensagens públicas e a solução sempre entram no índice; notas internas só se a fonte ligar a opção"
    motivo: "notas internas podem ter informação sensível"
    alternativas: "tudo sempre; só problema e solução"
    adr: null
  - id: D5
    data: 2026-10-12
    por: usuario
    decisao: "Anonimização determinística por regras, ligada por padrão: e-mail, CPF, CNPJ, telefone, cartão (Luhn), IP e os nomes declarados no payload (solicitante, organização, atendentes) viram marcadores"
    motivo: "LGPD (seção 9 do AGENTS.md) sem custo de LLM, testável e reproduzível"
    alternativas: "regras + LLM opcional; sem anonimização"
    adr: null
  - id: D6
    data: 2026-10-12
    por: usuario
    decisao: "O payload bruto fica na caixa de entrada só até ser processado; depois só restam o Markdown anonimizado no índice e os hashes para idempotência"
    motivo: "guardar o mínimo de dado pessoal"
    alternativas: "guardar o bruto por N dias"
    adr: null
  - id: D7
    data: 2026-10-12
    por: usuario
    decisao: "Acesso aos chamados no chat como nas outras fontes: pela coleção ligada ao assistente; sem ACL por chamado"
    motivo: "o modelo atual de permissão por coleção basta para este lote; ACL por chamado exige identidade dos usuários do chat"
    alternativas: "ACL por chamado no payload"
    adr: null
  - id: D8
    data: 2026-10-12
    por: usuario
    decisao: "Citação de chamado mostra número, título, status, data (resolução ou atualização), link para o sistema de origem (se houver URL) e o trecho"
    motivo: "o usuário precisa achar o chamado original"
    alternativas: "só número e trecho"
    adr: null
  - id: D9
    data: 2026-10-12
    por: usuario
    decisao: "Todos os chamados entram (abertos e resolvidos), com o status na citação; o prompt prioriza a solução de chamados resolvidos; a fonte pode filtrar por status"
    motivo: "o chat também precisa saber de problemas em andamento"
    alternativas: "só resolvidos ou fechados"
    adr: null
  - id: D10
    data: 2026-10-12
    por: usuario
    decisao: "Abrir chamado entra no lote: webhook de saída por assistente (URL e segredo), com a pergunta, a conversa, um resumo e o nome e o e-mail do usuário, enviado só depois da confirmação dele na tela; assinatura HMAC-SHA256 e retentativas; número e link do chamado mostrados se o destino devolver"
    motivo: "fecha a regra 8 (sem fonte, oferecer abrir chamado) com um mecanismo genérico, sem integrar provedor"
    alternativas: "lote futuro; webhook por workspace só com a pergunta; só identificador interno do usuário"
    adr: docs/adr/0006-chamados-por-push.md
  - id: D11
    data: 2026-10-12
    por: usuario
    decisao: "Embedding do Gemini pelo OpenRouter (credencial existente), com 1536 dimensões para caber no vector(1536)"
    motivo: "sem provedor novo; o catálogo do OpenRouter já expõe embeddings"
    alternativas: "novo provedor Google com o SDK oficial"
    adr: null
  - id: D12
    data: 2026-10-12
    por: usuario
    decisao: "Ensaio de chamados e comparação de embeddings sobre um conjunto sintético gerado por script com semente; dados reais ficam para um piloto"
    motivo: "o usuário não tem export de chamados reais para o ensaio"
    alternativas: "export real; índice do Minski para os embeddings"
    adr: null
  - id: D13
    data: 2026-10-12
    por: agente
    decisao: "A caixa de entrada é uma tabela no Postgres e o processamento é um conector interno tickets no workflow de ingestão existente (como o conector knowledge do plano 0004), disparado por request_sync com o gatilho ingest e sync_pending"
    motivo: "herda incremental, retentativa, custo por execução, telas de execuções e documentos e busca sem fila nova"
    alternativas: "fila separada (Redis, SQS); workflow Temporal próprio por chamado"
    adr: docs/adr/0006-chamados-por-push.md
  - id: D14
    data: 2026-10-12
    por: agente
    decisao: "Token de envio por fonte (kbi_<8>_<urlsafe32>), mostrado uma vez, SHA-256 guardado, busca por prefixo, rotação que invalida o anterior; só abre /v1/ingest/*"
    motivo: "mesmo padrão já validado do token de runner; uma fonte por integração facilita revogar"
    alternativas: "chave de API por workspace; OAuth client credentials"
    adr: null
  - id: D15
    data: 2026-10-12
    por: agente
    decisao: "Lote de até 100 chamados e 5 MB por requisição, resposta 202 com o resultado por item; upload de até 50 MB por arquivo; upsert por (fonte, external_id) só quando updated_at é maior ou igual ao guardado; remoção explícita por external_id"
    motivo: "reenviar não duplica nem regride; lote limitado protege a API"
    alternativas: "um chamado por requisição; sem regra de updated_at"
    adr: null
  - id: D16
    data: 2026-10-12
    por: agente
    decisao: "Entrega do webhook de saída por workflow Temporal com retentativas exponenciais por até 24 h; destino só https, resolvido e recusado se for IP privado, loopback ou link-local (lista de permissão por variável de ambiente para desenvolvimento)"
    motivo: "entrega confiável fora da requisição e proteção contra SSRF"
    alternativas: "envio síncrono na requisição; fila no Postgres com worker próprio"
    adr: null
  - id: D17
    data: 2026-10-12
    por: agente
    decisao: "F1.1: lote {items:[{op:upsert,ticket}|{op:delete,external_id,deleted_at?}]}; remoção grava lápide datada que barra upsert atrasado; resultado por item queued, unchanged, stale ou rejected (duplicate_in_batch para external_id repetido) e sync started, pending, deferred ou none; Temporal fora não falha o envio; 5 MiB por lote, 1 MiB por chamado, 50 MiB por upload"
    motivo: "idempotência e ordem robustas com retentativas do lado do cliente; recebimento desacoplado do processamento"
    alternativas: "remoção sem lápide; falhar o envio sem Temporal"
    adr: null
  - id: D18
    data: 2026-10-12
    por: agente
    decisao: "F1.1: anonimização com marcadores [SOLICITANTE], [ORGANIZACAO], [ATENDENTE_n], [CLIENTE_n], [EMAIL], [CPF]...; primeiro nome (3+ letras) também trocado; IPv4 depois de v, versão ou build preservado; conversa numa seção única; mudar a configuração da fonte só vale para chamados recebidos depois (o bruto é apagado); resumo do webhook gerado pelo LLM do assistente na prévia, editável, com fallback para a pergunta; token de envio e segredo do webhook (kbw_) exigem owner ou admin (ajuste do orquestrador: são credenciais)"
    motivo: "detalhes de contrato que o plano não fixava"
    alternativas: "papel editor para credenciais; resumo sem LLM"
    adr: null
  - id: D19
    data: 2026-10-12
    por: agente
    decisao: "F1.2: onde plano e spec divergem vale a spec: config statuses (não status_filter) e webhook ligado = URL e segredo presentes (propriedade ticket_webhook_configured, sem coluna enabled); colunas ticket_updated_at, ticket_webhook_secret_ciphertext e ingest_tokens.issued_at (rotação na mesma linha); payload e corpo do webhook só em pending; body do pedido em text para reenviar os bytes assinados; downgrade da 0016 recusa se houver dados dos tipos novos; CHECKs novos sem nome duplicado"
    motivo: "a spec é o contrato das próximas subfases; menos estado redundante"
    alternativas: "colunas enabled separadas; jsonb para o corpo assinado"
    adr: null
  - id: D20
    data: 2026-10-12
    por: agente
    decisao: "F2.1: teste de conexão da fonte tickets como ConnectionCheck injetado no SourceService (ingestion não importa tickets); RunnerBodyLimitMiddleware virou BodyLimitMiddleware e cobre /v1/ingest/tickets (5 MiB); duplicate_in_batch só conta item anterior aceito; sync deferred para qualquer recusa de iniciar; rotação mantém created_by e created_at da primeira emissão; 503 por OSError, OperationalError ou InterfaceError; fonte tickets recusa globs"
    motivo: "manter as dependências apontando para baixo e o contrato da spec"
    alternativas: "importar tickets em ingestion; middleware separado para ingest"
    adr: null
  - id: D21
    data: 2026-10-12
    por: agente
    decisao: "F2.2: um só modelo do chamado (TicketIn em tickets/wire.py, o publicado no OpenAPI), com display_number e reference_date; cartão em grupos exige grupos de 3 a 6 dígitos (evita telefone virar cartão por Luhn); IPv6 confirmado por ipaddress; CRLF normalizado e cerca de código aberta fechada nos corpos; campos de uma linha colapsados; chamado sem seções vira um chunk section problem; numeração de autores pela ordem das mensagens; telefone só BR com +55 opcional e chunking por seção como na spec (o plano dizia internacional e problema+solução juntos)"
    motivo: "seguir a spec como contrato e evitar falsos positivos da anonimização"
    alternativas: "dois modelos do chamado; telefone internacional"
    adr: null
  - id: D22
    data: 2026-10-12
    por: agente
    decisao: "F2.3: a entrada da caixa é fechada (e o bruto apagado) dentro do process_batch, na mesma transação que grava, remove ou registra o erro do documento e marca run_items.done, conferindo o content_hash da versão buscada no fetch; versão nova que chega depois do fetch fica pendente para a próxima execução; payload guardado que não valida mais vira ticket_invalid (422); gancho settle opcional em ingestion/settle.py; a fábrica de chamados recebe o relógio"
    motivo: "atomicidade: retentativa não perde chamado nem fecha duas vezes, sem coluna nova em run_items"
    alternativas: "fechar no finish_run com o hash listado (exigiria migração)"
    adr: null
  - id: D23
    data: 2026-10-12
    por: agente
    decisao: "F2.4: dependência nova python-multipart (exigida pelo Starlette para multipart); limite de 50 MiB do upload aplicado na rota em fluxo (não no middleware, que guarda o corpo em memória), arquivo em disco temporário lido em blocos de 100; leitor JSON incremental próprio com uma passada de conferência antes de gravar; duplicado detectado no arquivo inteiro; prévia: editor+, até 2 MiB, funciona com fonte inativa, devolve título, Markdown e marcadores aplicados com contagem; arquivo vazio upload_empty; falha no meio mantém os blocos já gravados (reenvio seguro, unchanged)"
    motivo: "carga histórica grande sem estourar memória e sem dependência pesada de parsing"
    alternativas: "biblioteca de JSON em streaming; limite no middleware"
    adr: null
pendencias_usuario:
  - id: P1
    data: 2026-10-12
    pergunta: "A chave do OpenRouter usada nos ensaios expira em 2026-10-12. Os ensaios F6.2 e F6.3 precisam de uma chave válida (embeddings OpenAI e Gemini e o chat). Quando chegar a F6.2, você cadastra uma chave nova no scratchpad da sessão?"
    bloqueia: F6.2
    status: aberta
    resposta: null
    respondida_em: null
---

# Plano 0005 — Chamados por API

## 1. Pedido original

Proposta do agente para o próximo lote: conector de chamados (com anonimização e citação). Resposta do usuário:

> "Gostei da ideia, mas não gostaria de ficar customizando conectores para cada provedor.... Não faz sentido receber via api de forma padronizada os chamados, colocar isso em uma fila e ir processando conforme sua sugestão?"

## 2. Entendimento (perguntas e respostas)

| # | Pergunta | Resposta | Data |
|---|---|---|---|
| 1 | Como os chamados entram? | API no formato KnoBridge e upload de arquivo no painel (sem mapeamento de webhook nativo) | 2026-10-12 |
| 2 | Só chamados ou também documentos genéricos? | Só chamados | 2026-10-12 |
| 3 | O que do chamado vai para o índice? | Mensagens públicas e solução; notas internas opcionais por fonte | 2026-10-12 |
| 4 | Há chamados reais para o ensaio? | Não; ensaio sintético | 2026-10-12 |
| 5 | Como anonimizar? | Regras determinísticas, ligadas por padrão | 2026-10-12 |
| 6 | O que vira o payload bruto? | Apagado após processar | 2026-10-12 |
| 7 | Quem vê chamados no chat? | Quem usa assistente ligado à coleção (como as outras fontes) | 2026-10-12 |
| 8 | O que a citação mostra? | Número, título, status, data e link | 2026-10-12 |
| 9 | Quais chamados entram? | Todos, com status na citação | 2026-10-12 |
| 10 | Formatos do upload? | JSON e JSONL | 2026-10-12 |
| 11 | "Abrir chamado" entra neste lote? | Sim, webhook de saída simples | 2026-10-12 |
| 12 | Comparação de embeddings OpenAI x Gemini junto? | Sim, como última fase | 2026-10-12 |
| 13 | Onde fica o webhook e o que envia? | Por assistente, com a pergunta, a conversa, um resumo e assinatura HMAC | 2026-10-12 |
| 14 | O webhook identifica quem pediu? | Nome e e-mail do usuário, com confirmação na tela | 2026-10-12 |
| 15 | Como acessar o embedding do Gemini? | Pelo OpenRouter | 2026-10-12 |
| 16 | Sobre qual conteúdo comparar? | Conjunto sintético | 2026-10-12 |

**O que será feito**: uma fonte do tipo `tickets` recebe chamados por push, num formato padrão publicado em JSON Schema e OpenAPI, pela API com um token de envio ou por upload JSON/JSONL no painel. Os chamados validados vão para uma caixa de entrada no Postgres. Um conector interno `tickets`, dentro do workflow de ingestão já existente, anonimiza cada chamado, monta o Markdown (problema, conversa, solução), quebra em chunks, gera os embeddings e apaga o bruto. O chat cita o chamado com número, título, status, data e link. Quando o assistente não tem fonte, o usuário pode abrir um chamado: o KnoBridge envia a pergunta, a conversa, um resumo e o nome e o e-mail dele para o webhook configurado no assistente, assinado e com retentativas. Por fim, entra o embedding do Gemini pelo OpenRouter e uma comparação com o OpenAI em pt-BR sobre um conjunto sintético.

**Fora do escopo**: conectores por provedor e mapeamento de webhook nativo (D1, D2); CSV (D2); documentos genéricos empurrados (D3); ACL por chamado (D7); anonimização por LLM (D5); anexos dos chamados (o formato aceita só os nomes dos anexos, que não são baixados); guardar o bruto (D6); provedor Google direto (D11); dados reais (D12).

## 3. Critérios de aceite

- [ ] O ADR 0006 e a spec `docs/specs/chamados.md` publicam o formato do chamado (JSON Schema), o envio, a fila, a anonimização, o Markdown, a citação e o webhook de saída; a tabela da seção 9 da visão aponta para o ADR.
- [ ] Um sistema externo envia lotes de chamados com o token da fonte. Reenviar não duplica, um `updated_at` mais antigo não sobrescreve um mais novo e a remoção tira o chamado do índice.
- [ ] O upload JSON/JSONL no painel passa pela mesma validação e pela mesma fila, com relatório por linha.
- [ ] O índice só tem o Markdown anonimizado. O bruto some depois do processamento. Notas internas só entram com a opção ligada. Há testes de cada regra de anonimização.
- [ ] O chat cita chamados (número, título, status, data, link) e prioriza a solução de chamados resolvidos; as citações antigas continuam iguais.
- [ ] Com o webhook configurado, o usuário abre um chamado a partir de uma resposta sem fonte, vê o que será enviado, confirma e vê o número e o link se o destino devolver. A entrega é assinada, retentada e protegida contra SSRF.
- [ ] O embedding do Gemini pelo OpenRouter funciona com 1536 dimensões numa coleção.
- [ ] O E2E da stack passa duas vezes seguidas; guia, README, CHANGELOG e `AGENTS.md` estão atualizados.
- [ ] Os relatórios `docs/pesquisa/0003` (ensaio sintético de chamados) e `0004` (OpenAI x Gemini, com recomendação) existem.
- [ ] Cobertura de 95% ou mais em cada pacote tocado; nenhum dado real no repositório.

## 4. Fases e subfases

Convenções para todas as subfases: código em inglês, docs em pt-BR; regras 1 a 10 do `AGENTS.md` raiz; a suíte padrão não chama LLM nem rede externa (fakes para embedding, LLM e destino do webhook). Os agentes não editam `backend/AGENTS.md`, `backend/src/knobridge/AGENTS.md` nem o `AGENTS.md` raiz: relatam o texto e o orquestrador insere (exceto F6.1, que edita o raiz). Backend, frontend e E2E rodam um de cada vez, porque a máquina tem pouca memória.

### F1 — Contrato e modelo de dados

Fixar o formato do chamado e o modelo antes do código.

#### F1.1 — ADR 0006 e spec de chamados

- **Objetivo**: decidir e documentar o recebimento por push e o webhook de saída.
- **Entregáveis**:
  - `docs/adr/0006-chamados-por-push.md`: contexto (a visão previa "1 sistema de chamados" como conector), decisão D1/D13/D10, alternativas, consequências.
  - Linha D17 na tabela da seção 9 da visão; nota no roadmap (Fase 0 e Fase 1: conector de chamados vira API de chamados).
  - `docs/specs/chamados.md`:
    - formato do chamado em JSON Schema: `external_id`, `number`, `title`, `status` normalizado (`open`, `pending`, `resolved`, `closed`) mais o status original, `priority`, `category`, `product`, `tags`, `url`, `created_at`, `updated_at`, `resolved_at`, `requester` (nome, e-mail, organização), `assignees`, `messages[]` (papel `customer`/`agent`/`system`, nome do autor, `public`, corpo em texto, Markdown ou HTML, data), `resolution`, `attachments` (só nomes) e `custom_fields`;
    - a operação de remoção;
    - envio (`POST /v1/ingest/tickets`, token, limites, resposta por item, códigos de erro, idempotência pela regra do `updated_at`);
    - upload; caixa de entrada e ciclo de vida;
    - anonimização (regras, marcadores e ordem);
    - Markdown e chunking do chamado;
    - citação `kind: ticket`;
    - webhook de saída (payload, cabeçalhos `KnoBridge-Signature: t=...,v1=...`, verificação, retentativas, resposta esperada `{ticket_id?, url?}`, SSRF).
  - Seção de versão em `chat-sse.md` (v0.6, citação de chamado), como contrato a implementar.
- **Contexto necessário**: `AGENTS.md` raiz (seções 2, 7 e 9) e `docs/AGENTS.md`; visão, seções 7 a 9 e 11; `docs/adr/0005-runner-local-do-harness.md` (formato de ADR); `docs/specs/runner.md` (padrão de token e de limites); `docs/specs/harness.md` (seções do conector `knowledge` e da citação); `docs/specs/chat-sse.md`; `docs/specs/indexacao.md`; este plano, seções 2 e 3.
- **Critérios de aceite**: o schema cobre todos os campos usados pelas subfases seguintes, com exemplo válido e inválido; links relativos válidos; `check_agents_md.py` e `check_plans.py` verdes.
- **Depende de**: nenhuma.
- **Tamanho**: médio.

#### F1.2 — Migração 0016

- **Objetivo**: tabelas e colunas do lote, com RLS e testes de isolamento.
- **Entregáveis**:
  - `SourceKind.TICKETS` e `TicketsSourceConfig` (`include_internal_notes`, `statuses`, `anonymize` com padrão ligado);
  - token de envio (`ingest_token_prefix` único na instância e `ingest_token_hash`, em tabela própria `ingest_tokens` ligada à fonte);
  - `ticket_inbox` (fonte, `external_id`, operação, `updated_at` do chamado, payload JSONB, recebido em, estado, erro);
  - em `assistants`: `ticket_webhook_url`, `ticket_webhook_secret` cifrado (AES-GCM, finalidade própria) e a data do segredo (ligado = URL e segredo presentes, D19);
  - `ticket_requests` (conversa, mensagem, usuário, estado, tentativas, `external_ticket_id`, `external_url`, último erro);
  - `RunTrigger.INGEST` e `DocumentKind.TICKET`;
  - modelos SQLAlchemy, migração `0016` e `modelo-de-dados.md` v0.8.
- **Contexto necessário**: `backend/AGENTS.md`, AGENTS de `ingestion/`, `harness/`, `assistants/`, `migrations/` e `tests/`; `migrations/versions/0014*.py` e `0015*.py`; `harness/models.py` (padrão de token e RLS); `core/crypto` ([ADR 0003](../adr/0003-segredos-cifrados.md)); `docs/specs/modelo-de-dados.md`; `docs/specs/chamados.md` (F1.1).
- **Critérios de aceite**: testes de RLS como dono e não dono em cada tabela nova, FKs compostas por workspace, unicidade `(source_id, external_id)` na caixa, prefixo único, `CHECK`s, `upgrade` e `downgrade`; cobertura ≥ 95%.
- **Depende de**: F1.1.
- **Tamanho**: médio.

### F2 — Servidor: recebimento e indexação

#### F2.1 — Fonte tickets, token de envio e endpoint de lote

- **Objetivo**: receber lotes padronizados e enfileirar.
- **Entregáveis**:
  - Fonte `tickets` pela API de fontes (config validada).
  - Gerar e rotacionar o token (`POST .../sources/{sid}/ingest-token`, owner/admin, mostrado uma vez, auditado).
  - Autenticação por token `kbi_` (401 único `invalid_ingest_token`).
  - `POST /v1/ingest/tickets`:
    - corpo `{items: [{op: upsert|delete, ...}]}` (D17), até 100 itens e 5 MiB (413);
    - validação estrita por item, com o resultado por item `queued | unchanged | stale | rejected` e os erros (D17);
    - upsert na caixa pela regra do `updated_at`;
    - 202, e `request_sync` com o gatilho `ingest`;
    - fonte inativa: 409.
  - Teste de conexão da fonte (ok quando há token ativo).
  - OpenAPI e cliente regenerados.
- **Contexto necessário**: `backend/AGENTS.md`; AGENTS de `api/`, `ingestion/`, `harness/`, `audit/` e `tests/api/`; `harness/tokens.py` e `api/runner_auth*` (padrão de token); `api/runner_wire.py` e o middleware de limite de corpo; `ingestion/sources.py`, `source_config.py` e `sync.py` (`request_sync`); `docs/specs/chamados.md`.
- **Critérios de aceite**: testes de lote válido, item inválido sem derrubar o lote, item antigo `stale`, reenvio idempotente, remoção, 413, 401, 409, isolamento entre workspaces, token que não abre outras rotas, token nunca em log, `request_sync` chamado (fake) e auditoria do token.
- **Depende de**: F1.2.
- **Tamanho**: médio.

#### F2.2 — Anonimização, Markdown e chunking do chamado

- **Objetivo**: transformar o payload num Markdown anonimizado e em chunks, com módulos puros.
- **Entregáveis**:
  - `tickets/anonymize.py`: regras de e-mail, CPF e CNPJ (com e sem máscara, dígito verificador), telefone BR e internacional, cartão (Luhn), IPv4/IPv6 e os nomes declarados (solicitante, organização, atendentes, autores) com marcadores estáveis por chamado (`[CLIENTE]`, `[ATENDENTE 1]`, `[EMAIL]`, `[CPF]`...).
  - `tickets/markdown.py`: cabeçalho com número, título, status, categoria, produto e datas; problema; conversa com papéis, só pública ou também interna; solução. HTML do corpo convertido para Markdown pelo conversor já usado.
  - `ParsedKind.TICKET` e `chunk_ticket` (o problema e a solução no primeiro chunk; a conversa em blocos com sobreposição; metadados do chamado em cada chunk).
- **Contexto necessário**: AGENTS de `backend/` e de `ingestion/`; `ingestion/parsing.py`, `chunking.py` e `chunk_base.py`; `harness/knowledge_markdown.py` (padrão de módulo puro); `docs/specs/chamados.md`.
- **Critérios de aceite**:
  - testes por regra, com positivos e negativos (número que parece CPF mas não valida, e-mail dentro de URL, telefone com e sem DDI);
  - nome declarado em várias grafias (caixa e acento);
  - marcador estável dentro do chamado;
  - nota interna excluída por padrão;
  - Markdown igual ao da spec;
  - chunks com metadados;
  - hash estável;
  - cobertura de 100% nos módulos puros.
- **Depende de**: F1.1.
- **Tamanho**: médio.

#### F2.3 — Conector interno tickets e citação de chamado

- **Objetivo**: processar a caixa de entrada no workflow de ingestão e citar no chat.
- **Entregáveis**:
  - `tickets/connector.py`: `TicketsConnector` com `list_changes` a partir da caixa (upserts e remoções), `fetch` (payload → anonimização → Markdown, hash do Markdown mais os metadados de citação) e cursor versionado.
  - Exclusão do bruto depois que o documento é gravado, na mesma activity e de forma idempotente.
  - Filtro de status da fonte.
  - `SettingsConnectorFactory` recebe a fábrica `tickets` (sem `ingestion` importar `tickets`).
  - Citação `kind: ticket` (número, título, status, `resolved_at` ou `updated_at`, `url`, trecho) no contexto e no SSE v0.6.
  - Regra no prompt: priorizar a solução de chamados resolvidos e dizer o status quando o chamado estiver aberto.
- **Contexto necessário**: AGENTS de `backend/`, `ingestion/`, `harness/`, `retrieval/`, `conversations/`, `workers/` e `tests/`; `harness/knowledge_connector.py` (padrão), `ingestion/connectors.py`, `runs.py` e `indexer.py`; `retrieval/context.py`; `conversations/prompt.py`; `docs/specs/chamados.md` e `chat-sse.md`.
- **Critérios de aceite**:
  - contrato de conectores na suíte compartilhada;
  - incremental (novo, alterado, removido) e bruto apagado só depois do sucesso;
  - reexecução idempotente;
  - filtro de status;
  - notas internas conforme a fonte;
  - citação no SSE com os campos;
  - citações antigas inalteradas;
  - workflow de ingestão real no ambiente de teste do Temporal;
  - isolamento entre workspaces.
- **Depende de**: F2.1, F2.2.
- **Tamanho**: médio.

#### F2.4 — Upload JSON/JSONL e prévia

- **Objetivo**: carga histórica sem código e conferência da anonimização.
- **Entregáveis**:
  - `POST .../sources/{sid}/tickets/upload` (sessão, editor ou acima, CSRF, multipart até 50 MB, JSON em lista ou JSONL lido em fluxo, a mesma validação e o mesmo upsert, relatório por linha com contagens e até 1000 erros, como na spec);
  - `POST .../sources/{sid}/tickets/preview` (um chamado → Markdown anonimizado e marcadores aplicados, sem gravar);
  - auditoria do upload (contagens, nunca o conteúdo).
- **Contexto necessário**: AGENTS de `api/` e `tests/api/`; o endpoint de F2.1; `tickets/anonymize.py` e `markdown.py` (F2.2); `docs/specs/chamados.md`.
- **Critérios de aceite**: testes de JSON, JSONL, linha inválida no meio, arquivo grande em fluxo (sem carregar tudo), 413, papéis, CSRF, prévia sem gravar nada e isolamento.
- **Depende de**: F2.1, F2.2.
- **Tamanho**: pequeno.

### F3 — Servidor: abrir chamado por webhook

#### F3.1 — Webhook do assistente e SSRF

- **Objetivo**: configurar o destino com segurança.
- **Entregáveis**:
  - campos no assistente pela API (URL https, segredo gerado pelo servidor e mostrado uma vez, cifrado em repouso, rotação, ligar e desligar);
  - `core/outbound.py` com o validador de destino (resolve o DNS e recusa IP privado, loopback, link-local e metadados de nuvem, com a lista de permissão `KNOBRIDGE_WEBHOOK_ALLOWED_HOSTS` só para desenvolvimento e E2E);
  - assinatura HMAC-SHA256 com carimbo de tempo;
  - `POST .../assistants/{aid}/ticket-webhook/test`, que envia um evento de teste e devolve o status;
  - `.env.example`.
- **Contexto necessário**: AGENTS de `backend/`, `assistants/`, `api/` e `core/`; `assistants/service.py`; `core/crypto` e [ADR 0003](../adr/0003-segredos-cifrados.md); `docs/specs/chamados.md` (webhook de saída).
- **Critérios de aceite**: testes de URL não https, IP privado direto e por DNS (resolvedor fake), lista de permissão, segredo nunca em resposta depois de criado nem em log, assinatura verificável por um receptor de teste, teste de entrega com servidor HTTP local fake, papéis e auditoria.
- **Depende de**: F1.2.
- **Tamanho**: médio.

#### F3.2 — Solicitação de chamado e entrega

- **Objetivo**: o usuário pede, o KnoBridge entrega de forma confiável.
- **Entregáveis**:
  - `POST .../conversations/{cid}/ticket-requests` (dono da conversa; opcionalmente a mensagem sem fonte de referência; devolve a prévia do que será enviado: pergunta, conversa, resumo, nome e e-mail);
  - `POST .../ticket-requests/{rid}/confirm`, que grava e inicia o workflow `knobridge.ticket_webhook.v1` (activity de entrega com timeout e retentativas exponenciais por até 24 h; 2xx conclui e guarda `ticket_id` e `url` da resposta se vierem; 4xx diferente de 408 e 429 falha sem retentar);
  - `GET` do estado;
  - resumo gerado pelo LLM do assistente (provedor fake na suíte), com fallback para a própria pergunta se o LLM falhar;
  - flag no evento `done` do SSE dizendo se o assistente oferece abrir chamado.
- **Contexto necessário**: AGENTS de `backend/`, `conversations/`, `workers/` e `api/`; `conversations/chat.py` e `turn.py`; `workers/ingestion.py` (padrão de workflow e activities); `core/outbound.py` (F3.1); `docs/specs/chamados.md` e `chat-sse.md`.
- **Critérios de aceite**: testes de prévia, confirmação, entrega 2xx com e sem número, retentativa em 5xx e em timeout, desistência em 4xx, assinatura, conversa de outro usuário (404), assistente sem webhook (409), resumo com LLM fake e com falha, workflow no ambiente de teste do Temporal, isolamento e auditoria.
- **Depende de**: F3.1.
- **Tamanho**: médio.

### F4 — Painel

#### F4.1 — Fonte de chamados e citação de chamado

- **Objetivo**: cadastrar a fonte, integrar e ver a citação.
- **Entregáveis**:
  - tipo "API de chamados" no formulário de fonte (notas internas, filtro de status, anonimização);
  - na fonte: gerar e rotacionar o token com o exemplo `curl` e o trecho Python copiáveis, o upload JSON/JSONL com o relatório por linha e a prévia de anonimização (colar um chamado e ver o Markdown);
  - citação `kind: ticket` no `CitationSheet` e no `AssistantMessage` (número, título, selo de status, data e link externo);
  - i18n, handlers MSW e factories.
- **Contexto necessário**: `frontend/AGENTS.md` e AGENTS de `src/features/`, `src/features/sources/`, `src/lib/`, `src/components/` e `src/test/`; `features/sources` (formulário e abas), `components/CitationSheet.tsx`, `lib/citationLocation.ts`; tipos gerados.
- **Critérios de aceite**: testes de criar a fonte, token mostrado uma vez, upload com sucesso e com erros por linha, prévia, papéis, citação de chamado com e sem link e citações antigas; cobertura ≥ 95%.
- **Depende de**: F2.3, F2.4.
- **Tamanho**: médio.

#### F4.2 — Webhook no assistente e "Abrir chamado"

- **Objetivo**: configurar o destino e abrir o chamado no chat.
- **Entregáveis**:
  - no formulário do assistente: URL, segredo mostrado uma vez, rotacionar, ligar e desligar, "Testar entrega" com o resultado;
  - no chat: botão "Abrir chamado" na resposta sem fonte (e no menu da conversa), diálogo com o que será enviado (pergunta, resumo, nome, e-mail) e confirmação, estado da solicitação (enviando, entregue com número e link, falhou com o motivo).
- **Contexto necessário**: `frontend/AGENTS.md`; `features/assistants` e `features/chat`; `lib/api/chatStream.ts`; tipos gerados.
- **Critérios de aceite**: testes do formulário, do segredo, do teste de entrega, do botão só quando o assistente oferece, do diálogo, da confirmação, do polling de estado que para ao concluir e dos erros; cobertura ≥ 95%.
- **Depende de**: F3.2, F4.1.
- **Tamanho**: médio.

### F5 — Embedding do Gemini

#### F5.1 — Gemini pelo OpenRouter

- **Objetivo**: coleção com o embedding do Gemini.
- **Entregáveis**:
  - o modelo de embedding do Gemini (ex.: `google/gemini-embedding-001`) aceito pelo provedor OpenRouter, enviando `dimensions: 1536` e validando que a resposta tem 1536 dimensões (senão, erro de domínio claro);
  - preço na tabela de embedding;
  - modelo na lista do formulário de coleção;
  - nota na spec de indexação.
- **Contexto necessário**: AGENTS de `backend/`, `llm/` e `frontend/`; `llm/openai_embeddings.py`, `embeddings.py` e `pricing.py`; o formulário de coleção do frontend; `docs/specs/indexacao.md`.
- **Critérios de aceite**: testes com provedor fake/transporte simulado (envio de `dimensions`, dimensão errada recusada, preço) e coleção criada com o modelo. O orquestrador confere uma vez, fora da suíte, que o catálogo do OpenRouter devolve 1536 dimensões; se não devolver, a subfase para e vira pendência.
- **Depende de**: nenhuma.
- **Tamanho**: pequeno.

### F6 — Entrega e ensaios

#### F6.1 — Gerador sintético, E2E, guia e documentação

- **Objetivo**: provar o fluxo inteiro e ensinar a integrar.
- **Entregáveis**:
  - `scripts/synthetic_tickets/` (com AGENTS e testes): gerador determinístico com semente, de chamados pt-BR realistas (vários produtos, problemas, papéis, notas internas, chamados abertos e resolvidos), com dados pessoais semeados e registrados num gabarito para medir a anonimização. Gera JSONL fora do repositório; só um exemplo pequeno fica em fixture.
  - E2E Playwright da stack: cria a fonte e o token, envia um lote pela API, faz o upload de um JSONL, a sincronização conclui, o chat cita o chamado; um receptor fake de webhook no compose de E2E recebe "Abrir chamado" assinado e devolve número e link.
  - `docs/guias/receber-chamados-por-api.md`: formato, token, exemplos `curl`, Python e um fluxo n8n descrito em texto, carga histórica, anonimização, verificação da assinatura do webhook.
  - README, CHANGELOG, `AGENTS.md` raiz (seções 1 e 12) e `.env.example`.
- **Contexto necessário**: `frontend/e2e/stack/` (specs e AGENTS); `deploy/docker-compose.e2e.yml`; `.github/workflows/ci.yml`; `scripts/AGENTS.md`; `docs/guias/mapear-codigo-com-runner.md` (estilo); `docs/specs/chamados.md`.
- **Critérios de aceite**: E2E verde duas vezes seguidas localmente; gerador testado (determinismo e gabarito); guia revisado pelo orquestrador; checagens de AGENTS e de planos verdes.
- **Depende de**: F4.2, F5.1.
- **Tamanho**: médio.

#### F6.2 — Ensaio sintético de chamados

- **Objetivo**: medir o recebimento, a anonimização e o chat com chamados.
- **Entregáveis**: na stack local, cerca de 300 chamados sintéticos por API e por upload. Medir:
  - anonimização contra o gabarito (dados pessoais semeados que escaparam, por tipo);
  - tempo e custo de indexação;
  - cerca de 15 perguntas de suporte com respostas esperadas (citou o chamado certo, usou a solução, tratou chamado aberto);
  - abrir chamado com um receptor local.

  Correções que o ensaio revelar entram com teste. Relatório `docs/pesquisa/0003-ensaio-chamados-sinteticos.md`.
- **Contexto necessário**: orquestrador, na sessão principal; `docs/pesquisa/0002-ensaio-harness-minski.md` (formato).
- **Critérios de aceite**: relatório com métricas e conclusões; gasto informado; nenhum dado real.
- **Depende de**: F6.1, P1.
- **Tamanho**: médio.

#### F6.3 — Comparação de embeddings OpenAI x Gemini

- **Objetivo**: escolher o embedding padrão para pt-BR com números.
- **Entregáveis**:
  - duas coleções com o mesmo conteúdo sintético (chamados de F6.2 e documentos sintéticos de produto gerados pelo mesmo script): `openai/text-embedding-3-small` e o Gemini com 1536 dimensões;
  - cerca de 20 perguntas pt-BR com o documento esperado;
  - métricas: recall@5, recall@10, MRR, faixa de similaridade das perguntas relacionadas e das sem relação (para o limiar), tempo e custo de indexação;
  - relatório `docs/pesquisa/0004-embeddings-openai-x-gemini.md` com a recomendação. Se a recomendação mudar o padrão, ADR na mesma subfase.
- **Contexto necessário**: orquestrador; `docs/pesquisa/0001-ensaio-minski.md` (calibração do limiar); `retrieval/search.py`.
- **Critérios de aceite**: relatório com as métricas por modelo e a recomendação; gasto informado.
- **Depende de**: F6.2, F5.1.
- **Tamanho**: pequeno.

## 5. Decisões

D1 a D12 vêm das respostas do usuário (seção 2). D13 a D16 são do agente, no planejamento, e entram no ADR 0006 quando forem de arquitetura.

## 6. Pendências do usuário

- **P1**: a chave do OpenRouter dos ensaios expira em 2026-10-12. Os ensaios F6.2 e F6.3 precisam de uma chave nova. Ela não bloqueia nada antes da F6.2: a suíte usa fakes.

## 7. Registro de andamento

- 2026-10-12 — plano criado na branch `plano/0005-chamados-por-api`, a partir de `plano/0004-harness-runner-local` (ainda não integrada à `main`); aguardando aprovação.
- 2026-10-12 — plano aprovado pelo usuário ("Aprovado"); F1.1 iniciada (agente em worktree).
- 2026-10-12 — F1.1 concluída: ADR 0006, spec chamados.md (JSON Schema, envio, fila, anonimização, Markdown, citação, webhook), chat-sse v0.6 e visão v0.4 (D17 e roadmap); token e segredo passaram a owner ou admin na revisão do orquestrador
- 2026-10-12 — F1.2 iniciada (agente em worktree).
- 2026-10-12 — F1.2 concluída: migração 0016 com ingest_tokens, ticket_inbox, ticket_requests e webhook em assistants, RLS forçada e testes de isolamento, modelo-de-dados v0.8, subpacote tickets/; backend 1537 passed com 99% de cobertura, frontend 1140
- 2026-10-12 — F2.1 iniciada (agente em worktree).
- 2026-10-12 — F2.1 concluída: token de envio kbi_ (owner/admin, auditado), POST /v1/ingest/tickets com validação por item, regra do updated_at e lápide, sincronização ingest depois do commit; gates do agente: backend 1628 passed com 99,86%, frontend 1140; orquestrador: ruff, format e pyright limpos na integração
- 2026-10-12 — F2.2 concluída: anonimização determinística, Markdown do chamado e chunk_ticket, integrados sobre a F2.1 com o TicketIn único de wire.py; backend 1740 passed com 99% de cobertura
- 2026-10-12 — F2.3 iniciada (agente em worktree).
- 2026-10-12 — F2.4 iniciada (agente em worktree).
- 2026-10-12 — F2.3 concluída: conector interno tickets no workflow de ingestão com fechamento da caixa na transação do documento, citação kind ticket no contexto e no SSE v0.6, regra de chamados no prompt e suíte de contrato estendida; gates do agente: backend 1776 passed com 99,86%, frontend 1140; orquestrador: ruff, pyright e AGENTS na integração
- 2026-10-12 — F2.4 concluída: upload JSON/JSONL em fluxo com relatório por linha e prévia de anonimização, integrados sobre a F2.3; backend 1866 passed com 99% de cobertura, frontend 1140
- 2026-10-12 — F3.1 iniciada (agente em worktree).
- 2026-10-12 — F5.1 iniciada (agente em worktree).

## 8. Encerramento

A preencher ao concluir.
