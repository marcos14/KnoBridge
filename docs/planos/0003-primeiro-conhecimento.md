---
id: 0003
titulo: Primeiro conhecimento de ponta a ponta — fontes Git e pasta, indexação incremental, busca híbrida e chat com citações reais
slug: primeiro-conhecimento
solicitado_por: usuario
criado_em: 2026-10-10
atualizado_em: 2026-10-10
status: em_execucao
aprovado_em: 2026-10-10
aprovado_por: usuario
concluido_em: null
branch: plano/0003-primeiro-conhecimento
fases:
  - id: F1
    titulo: Fundação da indexação (backend)
    status: concluida
    subfases:
      - id: F1.1
        titulo: Modelo de dados do índice e ADR 0004
        status: concluida
        agente: claude-code
        iniciada_em: 2026-10-10
        concluida_em: 2026-10-10
        commit: 425ae6b
      - id: F1.2
        titulo: EmbeddingProvider, adaptador OpenAI-compatível e fake
        status: concluida
        agente: claude-code
        iniciada_em: 2026-10-10
        concluida_em: 2026-10-10
        commit: 01e3b5a
      - id: F1.3
        titulo: Contrato de conector, seleção de arquivos e conector de pasta local
        status: concluida
        agente: claude-code
        iniciada_em: 2026-10-10
        concluida_em: 2026-10-10
        commit: 8b67b8b
      - id: F1.4
        titulo: Conector Git (árvore no HEAD e histórico de commits)
        status: concluida
        agente: claude-code
        iniciada_em: 2026-10-10
        concluida_em: 2026-10-10
        commit: f627b7c
  - id: F2
    titulo: Processamento de documentos
    status: concluida
    subfases:
      - id: F2.1
        titulo: Parsing de documentos para Markdown
        status: concluida
        agente: claude-code
        iniciada_em: 2026-10-10
        concluida_em: 2026-10-10
        commit: d4ebe60
      - id: F2.2
        titulo: Chunking por estrutura, por AST (tree-sitter) e de commits
        status: concluida
        agente: claude-code
        iniciada_em: 2026-10-10
        concluida_em: 2026-10-10
        commit: 0fa9788
  - id: F3
    titulo: Execução das sincronizações
    status: em_execucao
    subfases:
      - id: F3.1
        titulo: Workflow de ingestão incremental no Temporal
        status: concluida
        agente: claude-code
        iniciada_em: 2026-10-10
        concluida_em: 2026-10-10
        commit: 8529c83
      - id: F3.2
        titulo: API de coleções, fontes e execuções
        status: concluida
        agente: claude-code
        iniciada_em: 2026-10-10
        concluida_em: 2026-10-10
        commit: 12c325c
      - id: F3.3
        titulo: Agendamento por fonte (Temporal Schedules)
        status: em_execucao
        agente: claude-code
        iniciada_em: 2026-10-10
        concluida_em: null
        commit: null
  - id: F4
    titulo: Recuperação e chat com fontes
    status: em_execucao
    subfases:
      - id: F4.1
        titulo: Busca híbrida (vetorial + FTS, RRF) e rota de teste de busca
        status: concluida
        agente: claude-code
        iniciada_em: 2026-10-10
        concluida_em: 2026-10-10
        commit: 602e1d1
      - id: F4.2
        titulo: Retriever real, coleções do assistente e prompt com citações
        status: concluida
        agente: claude-code
        iniciada_em: 2026-10-10
        concluida_em: 2026-10-10
        commit: 6896294
  - id: F5
    titulo: Telas
    status: em_execucao
    subfases:
      - id: F5.1
        titulo: Tela de coleções com teste de busca
        status: concluida
        agente: claude-code
        iniciada_em: 2026-10-10
        concluida_em: 2026-10-10
        commit: 0a214dd
      - id: F5.2
        titulo: Tela de fontes, execuções e agendamento
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F5.3
        titulo: Coleções no assistente e citações de código e commit no chat
        status: em_execucao
        agente: claude-code
        iniciada_em: 2026-10-10
        concluida_em: null
        commit: null
  - id: F6
    titulo: Stack, documentação e ensaio real
    status: pendente
    subfases:
      - id: F6.1
        titulo: Compose, imagem e E2E da indexação contra a stack
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F6.2
        titulo: Specs, guia de indexação e documentação
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F6.3
        titulo: Ensaio real com o Minski (local, fora da CI)
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
decisoes:
  - id: D1
    data: 2026-10-10
    por: usuario
    decisao: A primeira fonte real é o projeto local C:\Projetos\Minski; o LLM é openai/gpt-6-luna-pro pelo OpenRouter, com a chave do usuário
    motivo: Validar o produto com conteúdo real e conhecido
    alternativas: Fixtures sintéticas apenas
    adr: null
  - id: D2
    data: 2026-10-10
    por: usuario
    decisao: Embedding openai/text-embedding-3-small (1536 dimensões) pelo OpenRouter, com a mesma credencial do provedor
    motivo: Barato, bom em pt-BR, uma chave só para chat e indexação (D5 da visão)
    alternativas: gemini-embedding-001; comparação dos dois; qwen3-embedding-8b
    adr: null
  - id: D3
    data: 2026-10-10
    por: usuario
    decisao: Indexar documentação e código; código fatiado por AST com tree-sitter (TypeScript/TSX/JavaScript e Go), fallback recursivo para outras linguagens
    motivo: Cobrir o "como funciona" a partir do código já neste bloco; o harness (D10) fica para um bloco próprio
    alternativas: Só documentação; só os dois repositórios
    adr: null
  - id: D4
    data: 2026-10-10
    por: usuario
    decisao: Conector Git para repositórios (incremental por SHA, inclui mensagens de commit como documentos) e conector de pasta local para arquivos soltos; a pasta de fontes é montada somente leitura no compose
    motivo: Histórico Git é valioso ("quando/por que mudou"); a raiz do Minski tem documentos fora de repositório
    alternativas: Só pasta local; upload + Git
    adr: null
  - id: D5
    data: 2026-10-10
    por: usuario
    decisao: Sincronização manual e agendada por fonte (cron via Temporal Schedules), sempre incremental
    motivo: Manter o índice atualizado sem intervenção
    alternativas: Só manual
    adr: null
  - id: D6
    data: 2026-10-10
    por: usuario
    decisao: Exclusões por .gitignore mais padrões (binários, zips, lockfiles, node_modules, dist, vendor, limite de tamanho), com globs de inclusão e exclusão editáveis por fonte
    motivo: Evitar ruído e custo com arquivos sem valor
    alternativas: Só globs manuais
    adr: null
  - id: D7
    data: 2026-10-10
    por: usuario
    decisao: Custo de embedding só registrado por execução (tokens e custo estimado pela tabela de preços), sem teto
    motivo: Simplicidade neste bloco
    alternativas: Estimativa prévia e teto por execução
    adr: null
  - id: D8
    data: 2026-10-10
    por: usuario
    decisao: Sem reranker neste bloco; busca híbrida vetorial + FTS com fusão RRF e interface Reranker apenas preparada
    motivo: Reranker em bloco próprio
    alternativas: Rerank por API (Cohere/Voyage)
    adr: null
  - id: D9
    data: 2026-10-10
    por: agente
    decisao: Uma coleção define a credencial e o modelo de embedding; cada fonte pertence a uma única coleção; um assistente consulta N coleções
    motivo: Evita indexar o mesmo documento com modelos diferentes e mantém o incremental simples; a coluna de vetor tem dimensão fixa (1536) e cada chunk registra o modelo que o gerou (ADR 0004)
    alternativas: Fonte em várias coleções (N:N) com reindexação por coleção; dimensão variável por coleção
    adr: docs/adr/0004-indice-de-conhecimento.md
  - id: D10
    data: 2026-10-10
    por: agente
    decisao: Pipeline de ingestão fixo (sem canvas) executado como workflow Temporal, com lógica incremental própria por hash de documento e cursor por fonte
    motivo: D4 da visão; o canvas visual reaproveitará as mesmas activities depois
    alternativas: Canvas já neste bloco; CocoIndex
    adr: docs/adr/0004-indice-de-conhecimento.md
  - id: D11
    data: 2026-10-10
    por: agente
    decisao: Parsing com MarkItDown (PDF, DOCX, XLSX, PPTX, HTML) neste bloco; Docling fica para quando tabelas e layout complexos importarem
    motivo: Docling traz dependências pesadas (modelos de ML) para a imagem; MarkItDown é o fallback previsto na seção 7.3 da visão
    alternativas: Docling desde já
    adr: null
  - id: D12
    data: 2026-10-10
    por: agente
    decisao: Resposta "sem fonte" (regra 8) quando nenhum chunk passa de uma similaridade mínima configurável por assistente (padrão definido na F4.2) — a fusão RRF sozinha sempre devolve algo
    motivo: Sem limiar, toda pergunta teria "fontes" irrelevantes e a regra 8 nunca dispararia
    alternativas: Deixar o LLM decidir sozinho; limiar global fixo
    adr: null
pendencias_usuario:
  - id: P1
    data: 2026-10-10
    pergunta: A chave do OpenRouter no .env do MINSKI-MAESTRO está expirada (401 "API key expired"). Gerar uma chave nova e colocá-la no mesmo .env ou cadastrá-la na tela de Provedores do KnoBridge.
    bloqueia: F6.3
    status: respondida
    resposta: Chave nova fornecida pelo usuário na conversa (limite de US$ 7, validada); guardada fora do repositório e usada só pelo orquestrador no ensaio
    respondida_em: 2026-10-10
---

# Plano 0003 — Primeiro conhecimento de ponta a ponta

## 1. Pedido original

> "Sugira um próximo bloco de desenvolvimento" → sugestão aceita: "Boa ideia! Use o projeto C:\Projetos\Minski para usar como source! No .env de um dos repos da Minski tem um .env com o token da OpenRouter, use o modelo Luna. A chave é minha, pode usar"

## 2. Entendimento (perguntas e respostas)

| # | Pergunta | Resposta | Data |
|---|---|---|---|
| 1 | Qual a fonte real do primeiro ensaio? | `C:\Projetos\Minski` (repositórios `MINSKI-MAESTRO`, `MINSKI-MAESTRO-RUNTIME` e arquivos soltos da raiz) | 2026-10-10 |
| 2 | Qual LLM? | `openai/gpt-6-luna-pro` pelo OpenRouter, com a chave do usuário (hoje expirada: P1) | 2026-10-10 |
| 3 | Modelo de embedding? | `openai/text-embedding-3-small` pelo OpenRouter | 2026-10-10 |
| 4 | O que indexar? | Documentação e código, código por AST (tree-sitter) | 2026-10-10 |
| 5 | Como ler o Minski? | Conector Git (repositórios) + conector de pasta local (arquivos soltos), montados somente leitura | 2026-10-10 |
| 6 | Como disparar? | Manual e agendado (cron), incremental | 2026-10-10 |
| 7 | Indexar histórico de commits? | Sim, cada commit vira documento | 2026-10-10 |
| 8 | Exclusões? | `.gitignore` + padrões, com globs por fonte | 2026-10-10 |
| 9 | Controle de custo? | Só registrar o custo por execução | 2026-10-10 |
| 10 | Reranker? | Não neste bloco | 2026-10-10 |

**Resumo.** Este bloco cria coleções e fontes por workspace. Dois conectores: Git (árvore no HEAD de uma branch e mensagens de commit, incremental por SHA) e pasta local (incremental por hash). Os documentos viram Markdown, depois chunks por estrutura (títulos), por AST (código) ou por commit, e são embedados em lote com cache por hash. Tudo roda num workflow Temporal, disparado no painel ou por agendamento. O índice fica no Postgres (pgvector HNSW + FTS) e é consultado por busca híbrida com RRF e similaridade mínima. Um `Retriever` real substitui o `NullRetriever`, e o chat passa a responder com citações de arquivo, linhas e commit. O fechamento é um ensaio real com o Minski, com métricas registradas.

**Privacidade (regra 9).** O conteúdo do Minski é lido só em tempo de execução, no ambiente local do usuário. Nada dele entra no repositório: testes, fixtures e E2E usam repositórios e pastas sintéticos criados nos próprios testes. A chave do OpenRouter nunca é commitada: ela é cadastrada no painel (cifrada, ADR 0003) ou lida do `.env` do Minski só pelo orquestrador no ensaio. O relatório do ensaio registra métricas e as perguntas, sem trechos do conteúdo do Minski.

**Fora do escopo**: harness de código (Claude Code/Codex), canvas visual de pipelines, reranker, conectores de chamados e wikis, upload pelo painel, credenciais para repositórios privados remotos (só caminho local montado ou URL HTTPS pública), permissões herdadas da fonte (ACL), teto de custo, contextual retrieval, Qdrant e destino `.md`.

## 3. Critérios de aceite

- [ ] Coleção com credencial e modelo de embedding; fonte Git ou pasta local ligada a uma coleção, com globs, branch e agendamento; tudo com RLS e testes de isolamento.
- [ ] "Sincronizar" roda um workflow Temporal incremental: só reprocessa o que mudou, remove do índice o que sumiu da fonte, registra a execução com contagens, tokens, custo, duração e erros por documento.
- [ ] Código TypeScript/TSX/JavaScript e Go fatiado por função, classe e método com caminho, linguagem, símbolo e linhas; Markdown por títulos; PDF/DOCX/HTML convertidos; commits como documentos.
- [ ] Busca híbrida (vetorial + FTS pt-BR, RRF) filtrada por workspace e coleção, com "testar busca" no painel.
- [ ] Chat com fontes: o assistente consulta suas coleções, responde citando `[n]` com arquivo e linhas ou commit; sem chunk acima da similaridade mínima, mantém a resposta "sem fonte" sem chamar o LLM.
- [ ] Agendamento por fonte via Temporal Schedules, editável e pausável pelo painel.
- [ ] E2E contra a stack: fonte de pasta sintética → sincronizar → pergunta no chat com citação, usando provedor `fake` (LLM e embeddings determinísticos); rodando na CI.
- [ ] Ensaio real local com o Minski e o modelo Luna, com métricas (documentos, chunks, tokens, custo, tempo, qualidade percebida em ~10 perguntas) em `docs/pesquisa/`.
- [ ] Gates: cobertura ≥ 95%, lint, typecheck, `check_agents_md`, `check_plans`, OpenAPI atualizado; ADR 0004; specs de conectores e de indexação.

## 4. Fases e subfases

Convenções que valem para todas as subfases (o agente recebe este bloco junto com a sua subfase):

- Backend: rotas de workspace sob `/v1/workspaces/{workspace_id}/...`, com acesso pela membership da sessão e `scoped_session` para a RLS; toda tabela nova com `workspace_id`, RLS forçada e teste de isolamento (app e RLS); listagens paginadas (`limit`/`offset`, `total`); erros no formato único; auditoria nas mudanças de configuração (não em cada documento indexado); logs estruturados com `workspace_id` e `run_id`.
- Novos pacotes seguem o layout de `backend/AGENTS.md`: `connectors/` (um subpacote por conector), `ingestion/` (parsing, chunking, orquestração incremental), `retrieval/` (busca e montagem de contexto), workflows e activities em `workers/`. Cada pasta nova com `AGENTS.md`.
- Temporal: workflows determinísticos, IO só em activities, activities idempotentes com retry explícito, nomes estáveis e versionados (`knobridge.ingestion.v1`). Testes com o ambiente de teste do SDK (`WorkflowEnvironment`), sem servidor externo.
- Testes nunca leem `C:\Projetos\Minski` nem chamam OpenRouter: repositórios Git e pastas sintéticos criados em `tmp_path` (com o binário `git`), fakes de embedding e LLM em `tests/fakes/`.
- OpenAPI: mudança de rota regenera `docs/specs/openapi.json` e `pnpm gen:api`.
- Frontend: rotas `/w/:workspaceId/...`, dados via `lib/api` + TanStack Query, formulários react-hook-form + zod, textos pt-BR, testes com Testing Library + MSW, telas carregadas com `lazyPage`.
- Relógio injetado, sem sleep, sem aleatoriedade sem seed.

### F1 — Fundação da indexação (backend)

Modelo de dados, embeddings e conectores, sem execução ainda.

#### F1.1 — Modelo de dados do índice e ADR 0004

- **Objetivo**: as tabelas do conhecimento indexado.
- **Entregáveis**: modelos `Collection` (nome, descrição, credencial de embedding do mesmo workspace por FK composta, modelo de embedding, dimensão), `Source` (coleção, tipo `git`/`folder`, nome, configuração JSON validada por tipo, globs de inclusão/exclusão, cron e estado do agendamento, cursor incremental, `active`), `Run` (fonte, gatilho `manual`/`schedule`, status `queued`/`running`/`succeeded`/`failed`/`cancelled`, contagens de documentos novos/alterados/removidos/com erro, chunks, tokens, custo, início/fim, erro resumido), `RunError` (documento, etapa, código, mensagem curta), `Document` (fonte, chave natural — caminho ou SHA —, tipo `file`/`commit`, título, URI, hash do conteúdo, linguagem, metadados, `indexed_at`), `Chunk` (documento, coleção, ordem, conteúdo, metadados — caminho, linhas, símbolo, títulos —, hash, modelo de embedding, `embedding vector(1536)`, `tsv` gerado com `portuguese` no conteúdo e `simple` em caminho e símbolo); índices HNSW (cosseno) e GIN; RLS em todas; migração 0010; `docs/adr/0004-indice-de-conhecimento.md` (dimensão fixa, modelo por chunk, fonte → uma coleção, pipeline fixo sobre Temporal, reindexação ao trocar de modelo); seção nova em `docs/specs/modelo-de-dados.md`; `AGENTS.md` de `ingestion/`.
- **Contexto necessário**: `AGENTS.md` raiz (2, 5, 6, 9); `backend/AGENTS.md`; AGENTS de `migrations/`, `llm/`, `assistants/`; `llm/models.py`, `assistants/models.py`, migrações 0008 e 0009 (padrão de RLS e FK composta); ADR 0001; seções 7.3 e 9 (D3, D4, D5) da visão; decisões D9 e D10 deste plano; convenções.
- **Critérios de aceite**: `test_collection_credential_must_belong_to_workspace`, `test_source_config_validated_by_kind`, `test_document_natural_key_unique_per_source`, `test_chunk_tsv_generated`, `test_index_tables_isolated_by_workspace` (RLS), teste de upgrade/downgrade da 0010; cobertura ≥ 95%.
- **Depende de**: nenhuma.
- **Tamanho**: médio.

#### F1.2 — EmbeddingProvider, adaptador OpenAI-compatível e fake

- **Objetivo**: gerar vetores atrás de uma interface pequena.
- **Entregáveis**: em `llm/`, `EmbeddingProvider` (Protocol: `embed(texts, model) -> EmbeddingResult` com vetores e tokens), adaptador com o SDK `openai` (`base_url` para OpenRouter e compatíveis), lotes por tamanho e por número de itens, normalização da dimensão esperada, erros mapeados para os mesmos códigos de domínio da F4.2 do plano 0002; `FakeEmbeddingProvider` determinístico (vetor derivado do hash do texto, mas com textos parecidos próximos o bastante para testes de busca — ex.: bag-of-words com hashing) também servindo o tipo de provedor `fake`; tabela de preços por modelo (`text-embedding-3-small` e o que mais for óbvio) sobrescrevível por env para o custo estimado; fábrica a partir de `ProviderCredential`.
- **Contexto necessário**: `backend/AGENTS.md`; AGENTS de `llm/`, `tests/fakes/`; `llm/provider.py`, `llm/openai_adapter.py`, `llm/factory.py`, `llm/errors.py`, `core/settings.py`; seção 7.3 (embeddings) da visão; convenções.
- **Critérios de aceite**: `test_openai_embeddings_batches_requests`, `test_openrouter_embeddings_uses_base_url`, `test_embedding_dimension_mismatch_raises`, `test_embedding_auth_error_mapped`, `test_fake_embeddings_deterministic_and_similar_for_similar_text`, `test_embedding_cost_from_price_table`; adaptador exercitado com `httpx.MockTransport`; cobertura ≥ 95%.
- **Depende de**: nenhuma.
- **Tamanho**: pequeno.

#### F1.3 — Contrato de conector, seleção de arquivos e conector de pasta local

- **Objetivo**: ler arquivos de uma pasta local com segurança e de forma incremental.
- **Entregáveis**: `connectors/base.py` com o contrato da visão (`list_changes(cursor) -> ChangeSet` com refs adicionadas, alteradas e removidas e o novo cursor; `fetch(ref) -> RawDocument`; `permissions(ref)` devolvendo ACL aberta neste bloco; `test_connection()`); seleção de arquivos compartilhada (`connectors/selection.py`: raiz permitida `KNOBRIDGE_LOCAL_SOURCES_ROOT` — caminho fora dela ou que escape por `..`/symlink é recusado —, `.gitignore` aninhado, padrões padrão — binários por detecção de bytes, `*.zip`, lockfiles, `node_modules/`, `dist/`, `build/`, `vendor/`, `.git/`, limite de tamanho configurável —, globs de inclusão e exclusão da fonte); `connectors/folder/` incremental por hash de conteúdo (cursor = mapa caminho → hash, ou equivalente compacto); suíte de contrato em `tests/connectors/contract/` com uma fonte fake e aplicada ao conector de pasta.
- **Contexto necessário**: `backend/AGENTS.md` (conectores e suíte de contrato); AGENTS de `connectors/` (criar); `core/settings.py`; seção 7.1 da visão; decisões D4 e D6; convenções.
- **Critérios de aceite**: `test_folder_lists_added_changed_removed`, `test_selection_respects_nested_gitignore`, `test_selection_skips_binaries_zips_and_large_files`, `test_selection_rejects_path_outside_root`, `test_selection_rejects_symlink_escape`, `test_include_exclude_globs`, suíte de contrato verde para o fake e para a pasta; cobertura ≥ 95%.
- **Depende de**: nenhuma.
- **Tamanho**: médio.

#### F1.4 — Conector Git (árvore no HEAD e histórico de commits)

- **Objetivo**: ler um repositório Git de forma incremental, incluindo os commits.
- **Entregáveis**: `connectors/git/`: origem por caminho local (dentro da raiz permitida) ou URL HTTPS pública clonada num diretório de trabalho do worker (`KNOBRIDGE_GIT_WORKDIR`); branch configurável; arquivos do HEAD com a seleção da F1.3; incremental por SHA (`git diff --name-status <cursor>..HEAD`, com renomeações), e reconstrução completa se o SHA do cursor não existir mais (force-push); commits como documentos (SHA, autor, data, mensagem completa, arquivos tocados com status), novos desde o cursor e limitados aos N mais recentes na primeira sincronização (configurável); uso do binário `git` via subprocesso com timeout e sem shell; `test_connection` valida o repositório e a branch; passa na suíte de contrato.
- **Contexto necessário**: `backend/AGENTS.md`; AGENTS de `connectors/`; `connectors/base.py`, `connectors/selection.py`; seção 7.1 (Git) da visão; decisões D4 e D6; convenções.
- **Critérios de aceite**: `test_git_initial_sync_lists_head_files_and_commits`, `test_git_incremental_by_sha_with_rename_and_delete`, `test_git_rebuilds_when_cursor_sha_missing`, `test_git_first_sync_commit_limit`, `test_git_rejects_local_path_outside_root`, `test_git_test_connection_reports_missing_branch`, suíte de contrato verde (repositórios sintéticos criados em `tmp_path`); cobertura ≥ 95%.
- **Depende de**: F1.3.
- **Tamanho**: médio.

### F2 — Processamento de documentos

Do documento bruto aos chunks, sem banco e sem rede.

#### F2.1 — Parsing de documentos para Markdown

- **Objetivo**: transformar cada documento em Markdown com metadados.
- **Entregáveis**: `ingestion/parsing.py`: Markdown e texto passam direto (com detecção de encoding); PDF, DOCX, XLSX, PPTX e HTML via MarkItDown; código-fonte marcado como código com a linguagem pela extensão; commit vira Markdown (título = primeira linha, corpo, lista de arquivos); documento que não pode ser lido gera erro de domínio (`unsupported_format`, `parse_failed`) para virar `RunError`, sem derrubar a execução; fixtures sintéticas pequenas (um PDF e um DOCX gerados ou mínimos) em `tests/fixtures/`.
- **Contexto necessário**: `backend/AGENTS.md`; AGENTS de `ingestion/`; `connectors/base.py` (formato do `RawDocument`); seção 7.3 da visão; decisão D11; convenções.
- **Critérios de aceite**: `test_parse_markdown_passthrough`, `test_parse_pdf_to_markdown`, `test_parse_docx_to_markdown`, `test_parse_html_to_markdown`, `test_parse_code_marks_language`, `test_parse_commit_document`, `test_parse_failure_is_domain_error`; cobertura ≥ 95%.
- **Depende de**: F1.3.
- **Tamanho**: pequeno.

#### F2.2 — Chunking por estrutura, por AST (tree-sitter) e de commits

- **Objetivo**: chunks bons para busca, com metadados para citar.
- **Entregáveis**: `ingestion/chunking.py` e `ingestion/code_chunking.py`: Markdown por títulos (com o caminho de títulos como contexto) e por tamanho com sobreposição quando a seção é grande; código TypeScript/TSX/JavaScript e Go por tree-sitter (funções, métodos, classes, interfaces/tipos, com símbolo, escopo pai, linhas inicial/final e um cabeçalho com caminho e símbolo no texto embedado), juntando nós pequenos vizinhos e dividindo nós enormes; fallback recursivo por linhas para outras linguagens; um chunk por commit (dividido se a mensagem for muito longa); limites em tokens estimados (contador simples e determinístico); hash por chunk para o cache de embedding.
- **Contexto necessário**: `backend/AGENTS.md`; AGENTS de `ingestion/`; `ingestion/parsing.py`; seções 7.2 e 7.3 (chunking) da visão; decisão D3; convenções.
- **Critérios de aceite**: `test_markdown_chunks_follow_headings`, `test_large_section_split_with_overlap`, `test_typescript_chunks_by_function_and_class`, `test_go_chunks_by_func_and_method`, `test_code_chunk_metadata_has_symbol_and_lines`, `test_unknown_language_falls_back_to_lines`, `test_commit_chunk`, `test_chunk_hash_stable`; cobertura ≥ 95%.
- **Depende de**: F2.1.
- **Tamanho**: médio.

### F3 — Execução das sincronizações

#### F3.1 — Workflow de ingestão incremental no Temporal

- **Objetivo**: uma sincronização durável, incremental e idempotente.
- **Entregáveis**: workflow `knobridge.ingestion.v1` em `workers/` e activities: abrir a execução, listar mudanças pelo conector, processar documentos em lotes (fetch → parse → chunk → embed com cache por hash de chunk dentro da coleção → upsert de documento e chunks numa transação por documento), remover documentos que sumiram, gravar o novo cursor só no fim com sucesso, fechar a execução com contagens, tokens, custo e duração; erro num documento vira `RunError` e a execução segue; falha geral marca `failed` com erro resumido; cancelamento marca `cancelled`; uma execução por fonte por vez (id de workflow determinístico por fonte); activities com retry explícito e heartbeat nos lotes; registro no worker.
- **Contexto necessário**: `backend/AGENTS.md` (Temporal); AGENTS de `workers/`, `ingestion/`, `connectors/`, `llm/`; `workers/worker.py`, `workers/health.py`, modelos da F1.1, `connectors/*`, `ingestion/*`, `llm/` (embeddings); seção 7.2 (execução) da visão; decisão D10; convenções.
- **Critérios de aceite**: `test_ingestion_indexes_new_documents`, `test_ingestion_reprocesses_only_changed`, `test_ingestion_removes_deleted_documents`, `test_ingestion_reuses_embedding_cache_by_chunk_hash`, `test_ingestion_document_error_recorded_and_run_continues`, `test_ingestion_cursor_saved_only_on_success`, `test_ingestion_cancel_marks_cancelled`, `test_ingestion_single_run_per_source`, `test_ingestion_records_tokens_and_cost` (ambiente de teste do Temporal, conector fake, embeddings fake, Postgres real); cobertura ≥ 95%.
- **Depende de**: F1.1, F1.2, F1.4, F2.2.
- **Tamanho**: médio.

#### F3.2 — API de coleções, fontes e execuções

- **Objetivo**: configurar e disparar tudo pela API.
- **Entregáveis**: rotas `GET/POST/PATCH/DELETE .../collections` (com contagens de fontes, documentos e chunks), `GET/POST/PATCH/DELETE .../sources` (configuração validada por tipo; `test` de conexão; `sync` dispara o workflow e devolve a execução; `cancel` da execução em andamento), `GET .../sources/{sid}/runs` e `GET .../runs/{rid}` (com erros paginados), `GET .../sources/{sid}/documents` (paginado, busca por caminho); papéis: owner/admin/editor gerenciam e disparam, viewer só lê; cliente Temporal injetado por dependência (fake nos testes); excluir fonte remove documentos e chunks e cancela execução; excluir coleção com fontes é recusado (409 `collection_in_use`); auditoria de criar/alterar/excluir/sincronizar; OpenAPI e tipos do frontend regenerados; rótulos pt-BR das novas ações e erros.
- **Contexto necessário**: `backend/AGENTS.md`; AGENTS de `api/`, `audit/`, `connectors/`, `workers/`; modelos da F1.1, `api/assistants.py` e `api/providers.py` (padrões de rota), `api/deps.py`, workflow da F3.1; convenções.
- **Critérios de aceite**: `test_create_source_requires_editor`, `test_source_config_invalid_returns_422`, `test_sync_starts_workflow_and_returns_run`, `test_sync_while_running_returns_409`, `test_cancel_run`, `test_delete_source_removes_index`, `test_delete_collection_in_use_409`, `test_sources_isolated_by_workspace`, `test_runs_list_paginated_with_errors`; cobertura ≥ 95%.
- **Depende de**: F3.1.
- **Tamanho**: médio.

#### F3.3 — Agendamento por fonte (Temporal Schedules)

- **Objetivo**: sincronizar sozinho no horário definido.
- **Entregáveis**: cron por fonte (validado; fuso UTC ou configurável por fonte) mapeado para um Temporal Schedule com id determinístico por fonte, criado, atualizado, pausado e removido junto com a fonte; política de sobreposição "pular se já estiver rodando"; execução disparada pelo schedule registra gatilho `schedule`; próxima execução prevista exposta na API da fonte; reconciliação na subida do worker (fonte com cron sem schedule, ou schedule órfão).
- **Contexto necessário**: `backend/AGENTS.md`; AGENTS de `workers/`, `api/`; workflow da F3.1 e rotas da F3.2; decisão D5; convenções.
- **Critérios de aceite**: `test_schedule_created_with_source_cron`, `test_schedule_updated_and_paused`, `test_schedule_removed_with_source`, `test_invalid_cron_returns_422`, `test_scheduled_run_records_trigger`, `test_reconcile_schedules`; cobertura ≥ 95%.
- **Depende de**: F3.2.
- **Tamanho**: pequeno.

### F4 — Recuperação e chat com fontes

#### F4.1 — Busca híbrida (vetorial + FTS, RRF) e rota de teste de busca

- **Objetivo**: encontrar os chunks certos para uma pergunta.
- **Entregáveis**: `retrieval/search.py`: embedding da consulta com o provedor da coleção, top-k vetorial (cosseno, HNSW) e top-k FTS (`websearch_to_tsquery` em `portuguese` e `simple`), fusão RRF, filtros por workspace e coleções, similaridade mínima, deduplicação de chunks vizinhos do mesmo documento; interface `Reranker` (Protocol) sem implementação, só o ponto de extensão; `POST .../collections/{cid}/search` ("testar busca": consulta → chunks com pontuações vetorial, FTS e fusão, documento, caminho e linhas); consultas sem N+1.
- **Contexto necessário**: `backend/AGENTS.md`; AGENTS de `retrieval/` (criar), `api/`; modelos da F1.1, embeddings da F1.2; seção 7.4 da visão; decisões D8 e D12; convenções.
- **Critérios de aceite**: `test_hybrid_search_fuses_vector_and_fts`, `test_hybrid_search_filters_by_workspace` (isolamento), `test_hybrid_search_filters_by_collection`, `test_min_similarity_drops_weak_matches`, `test_fts_finds_code_identifiers`, `test_search_endpoint_requires_membership`, teste de número de consultas; cobertura ≥ 95%.
- **Depende de**: F1.1, F1.2.
- **Tamanho**: médio.

#### F4.2 — Retriever real, coleções do assistente e prompt com citações

- **Objetivo**: o chat responde a partir das fontes, citando.
- **Entregáveis**: vínculo N:N assistente ↔ coleções (migração, API do assistente aceita e devolve `collection_ids`, mesma validação de workspace) e similaridade mínima por assistente (padrão definido e justificado no AGENTS.md); `HybridRetriever` em `retrieval/` implementando o `Retriever` da F4.4 do plano 0002, montando citações numeradas (título = caminho ou título do commit; URI = caminho com `#L<ini>-L<fim>` ou `commit:<sha>`; snippet), com limite de tokens de contexto; troca do `NullRetriever` em produção; prompt de sistema reforçado (responder só com base nas fontes, citar `[n]`, dizer que não sabe quando o contexto não basta); regra 8 preservada: nenhum chunk acima do limiar → mensagem "sem fonte" sem chamar o LLM; `docs/specs/chat-sse.md` e `docs/specs/chat.md` atualizados se algo observável mudar.
- **Contexto necessário**: `AGENTS.md` raiz (regra 8); `backend/AGENTS.md`; AGENTS de `conversations/`, `assistants/`, `retrieval/`, `api/`; `conversations/retrieval.py`, `conversations/prompt.py`, `conversations/chat.py`, `assistants/*`, `retrieval/search.py`; `docs/specs/chat.md`; decisão D12; convenções.
- **Critérios de aceite**: `test_assistant_collections_must_belong_to_workspace`, `test_retriever_uses_assistant_collections_only`, `test_chat_with_indexed_source_streams_and_cites`, `test_chat_below_threshold_returns_fallback_without_llm_call`, `test_citation_uri_for_code_and_commit`, `test_context_respects_token_limit`; cobertura ≥ 95%.
- **Depende de**: F4.1, F3.1.
- **Tamanho**: médio.

### F5 — Telas

#### F5.1 — Tela de coleções com teste de busca

- **Objetivo**: criar coleções e ver o que a busca devolve.
- **Entregáveis**: `/w/:id/collections` (substitui o esqueleto): lista com contagens, criar/editar (nome, descrição, credencial de embedding, modelo com padrão `openai/text-embedding-3-small`), excluir com confirmação (mensagem de `collection_in_use`); detalhe com fontes da coleção e "Testar busca" (consulta → resultados com pontuações, caminho, linhas e trecho); visibilidade por papel.
- **Contexto necessário**: `frontend/AGENTS.md`; AGENTS de `features/`, `components/`, `lib/api/`; telas de provedores e assistentes (padrões), `app/router.tsx`, `app/shell/navItems.ts`, handlers MSW; rotas da F3.2 e F4.1 no `schema.gen.ts`; convenções.
- **Critérios de aceite**: testes de criação com validação, exclusão em uso, teste de busca com resultados e vazio, viewer só leitura; cobertura ≥ 95.
- **Depende de**: F3.2, F4.1.
- **Tamanho**: médio.

#### F5.2 — Tela de fontes, execuções e agendamento

- **Objetivo**: configurar fontes e acompanhar as sincronizações.
- **Entregáveis**: `/w/:id/sources` (substitui o esqueleto): lista com tipo, coleção, última execução e próxima agendada; formulário por tipo (Git: caminho local ou URL, branch, limite de commits iniciais; pasta: caminho), globs, cron com ajuda e prévia legível, ativo; "Testar conexão", "Sincronizar agora", "Cancelar"; detalhe com execuções (status, contagens, tokens, custo, duração), erros por documento e documentos indexados com busca por caminho; atualização do status enquanto a execução roda (polling com intervalo do TanStack Query, sem timers reais nos testes).
- **Contexto necessário**: `frontend/AGENTS.md`; AGENTS de `features/`, `components/`, `lib/api/`; tela de coleções da F5.1, `app/router.tsx`, handlers MSW; rotas da F3.2 e F3.3 no `schema.gen.ts`; convenções.
- **Critérios de aceite**: testes do formulário por tipo com validação (cron inválido), sincronizar e cancelar, lista de execuções e erros, documentos, viewer só leitura; cobertura ≥ 95.
- **Depende de**: F5.1, F3.3.
- **Tamanho**: médio.

#### F5.3 — Coleções no assistente e citações de código e commit no chat

- **Objetivo**: ligar o assistente às coleções e mostrar bem as fontes.
- **Entregáveis**: formulário do assistente com seleção de coleções e similaridade mínima; painel de citação do chat (e da tela de conversas) exibindo caminho e linhas com o trecho em bloco de código com a linguagem, ou o commit (SHA curto, autor, data, título); estados vazios: assistente sem coleção avisa que responderá sempre "sem fonte".
- **Contexto necessário**: `frontend/AGENTS.md`; AGENTS de `features/assistants`, `features/chat`, `components/`; `AssistantDialog.tsx`, `CitationSheet.tsx`, `AssistantMessage.tsx`; rotas da F4.2 no `schema.gen.ts`; convenções.
- **Critérios de aceite**: testes da seleção de coleções, citação de código com linhas, citação de commit, aviso de assistente sem coleção; cobertura ≥ 95.
- **Depende de**: F4.2, F5.1.
- **Tamanho**: pequeno.

### F6 — Stack, documentação e ensaio real

#### F6.1 — Compose, imagem e E2E da indexação contra a stack

- **Objetivo**: provar a indexação de ponta a ponta na stack.
- **Entregáveis**: imagem com `git` e as dependências de parsing e tree-sitter; compose com a pasta de fontes do host (`KNOBRIDGE_SOURCES_DIR`, padrão uma pasta vazia do repositório) montada somente leitura em `/sources` na API e no worker, `KNOBRIDGE_LOCAL_SOURCES_ROOT=/sources` e volume para o diretório de trabalho do Git; a camada e2e monta uma pasta sintética versionada em `frontend/e2e/stack/fixtures/` (dois Markdown e um arquivo de código pequenos); E2E `stack` estendido: criar provedor `fake`, coleção, fonte de pasta, sincronizar, ver a execução concluída, testar busca, ligar a coleção ao assistente e perguntar no chat vendo a citação; job `e2e-stack` continua verde; `.env.example` e guia atualizados.
- **Contexto necessário**: `AGENTS.md` raiz (5, 8); `deploy/AGENTS.md`, `frontend/AGENTS.md`, `.github/workflows/AGENTS.md`, `frontend/e2e/stack/AGENTS.md`; `deploy/docker-compose.yml`, `deploy/docker-compose.e2e.yml`, `backend/Dockerfile`, `frontend/e2e/stack/*`, `docs/guias/subir-ambiente.md`; convenções.
- **Critérios de aceite**: E2E da stack verde localmente (verificado pelo orquestrador); actionlint limpo; `docker compose config` válido.
- **Depende de**: F5.3.
- **Tamanho**: médio.

#### F6.2 — Specs, guia de indexação e documentação

- **Objetivo**: documentação na mesma entrega do comportamento.
- **Entregáveis**: `docs/specs/conectores.md` (contrato, seleção de arquivos, Git e pasta, cursores), `docs/specs/indexacao.md` (parsing, chunking, embeddings, cache, execução Temporal, agendamento, custo, busca híbrida e limiar); `docs/specs/chat.md` atualizado (retriever real); `docs/guias/indexar-uma-fonte.md` (montar a pasta, criar coleção e fonte, sincronizar, ligar ao assistente, usar OpenRouter); `README.md`, `CHANGELOG.md`, `AGENTS.md` da raiz (estado) e AGENTS das pastas tocadas revisados; seção 9 da visão com o ADR 0004 na linha correspondente (D4/D5), sem mudar decisões.
- **Contexto necessário**: `AGENTS.md` raiz (7, 11); `docs/AGENTS.md`; ADR 0004; `docs/specs/*`; código de `connectors/`, `ingestion/`, `retrieval/`, `workers/` (leitura); convenções.
- **Critérios de aceite**: links relativos resolvem; Mermaid válido; `check_agents_md` e `check_plans` passam; pre-commit limpo.
- **Depende de**: F6.1.
- **Tamanho**: pequeno.

#### F6.3 — Ensaio real com o Minski (local, fora da CI)

- **Objetivo**: validar com conteúdo real e o modelo Luna.
- **Entregáveis**: executado pelo orquestrador na stack local, sem commit de nada do Minski: `KNOBRIDGE_SOURCES_DIR=C:\Projetos\Minski`; provedor OpenRouter com a chave nova do usuário; coleção com `openai/text-embedding-3-small`; fontes Git `MINSKI-MAESTRO` e `MINSKI-MAESTRO-RUNTIME` e fonte de pasta para os arquivos soltos da raiz; primeira sincronização e uma segunda (incremental, sem mudanças); assistente com `openai/gpt-6-luna-pro`; ~10 perguntas (como funciona, por que foi decidido, quando mudou, onde fica no código); `docs/pesquisa/0001-ensaio-minski.md` (e `docs/pesquisa/AGENTS.md` se a pasta não existir) com métricas — documentos e chunks por tipo, tokens e custo de embedding e de chat, tempo de cada sincronização, perguntas, se a resposta citou fonte e uma nota de qualidade —, sem trechos do conteúdo do Minski; correções encontradas viram subfase nova ou commit `fix` com teste.
- **Contexto necessário**: guia `docs/guias/indexar-uma-fonte.md`; este plano; nenhum código novo previsto.
- **Critérios de aceite**: as duas sincronizações concluídas (a segunda sem reprocessar nada); respostas com citações verificáveis; relatório escrito; nenhum arquivo do Minski e nenhuma chave no repositório (conferido com `git status` e gitleaks).
- **Depende de**: F6.2, P1.
- **Tamanho**: pequeno.

## 5. Decisões

Ver `decisoes[]` no frontmatter. ADR previsto: 0004 (índice de conhecimento: dimensão fixa, modelo por chunk, fonte → uma coleção, pipeline fixo sobre Temporal), escrito na F1.1.

## 6. Pendências do usuário

- P1 (respondida): chave nova do OpenRouter fornecida e validada; fica fora do repositório.

## 7. Registro de andamento

- 2026-10-10 — plano criado a partir de duas rodadas de perguntas; aguardando aprovação.
- 2026-10-10 — Plano aprovado pelo usuário; P1 respondida. F1.1 iniciada.
- 2026-10-10 — F1.1 concluída: Modelos Collection/Source/Run/RunError/Document/Chunk (vector(1536) HNSW, tsv gerado com GIN), migração 0010 com RLS, ADR 0004; 657 testes, 100%.
- 2026-10-10 — F1.2 iniciada.
- 2026-10-10 — F1.2 concluída: EmbeddingProvider, adaptador OpenAI/OpenRouter, fake por hashing, tabela de preços; 693 testes, 100%.
- 2026-10-10 — F1.3 iniciada.
- 2026-10-10 — F1.3 concluída: Contrato de conector, seleção (gitignore aninhado, binários, limites, raiz permitida, symlinks), conector de pasta incremental, suíte de contrato; 776 testes (2 de symlink pulados no Windows, verdes em container Linux: 80 passed).
- 2026-10-10 — F1.4 iniciada.
- 2026-10-10 — F2.1 executada em paralelo com a F1.4 (pastas disjuntas).
- 2026-10-10 — F2.1 concluída: Parsing para Markdown (texto com detecção de encoding, código cercado, PDF/DOCX/XLSX/PPTX/HTML via MarkItDown, commits), erros unsupported_format/parse_failed; 819 testes. Dependências +216 MB.
- 2026-10-10 — F2.2 iniciada (em paralelo com a F1.4).
- 2026-10-10 — F1.4 concluída: Conector Git (caminho local por objetos, URL https em clone parcial, incremental por SHA com reconstrução, commits como documentos), suíte de contrato; 887 testes.
- 2026-10-10 — F2.2 concluída: Chunking por títulos, AST (TS/TSX/JS/Go com tree-sitter <0.26), fallback por linhas e commits; ChunkDraft com metadados e hash; 918 testes.
- 2026-10-10 — F1 e F2 concluídas; F3.1 iniciada.
- 2026-10-10 — F4.1 iniciada em paralelo com a F3.1.
- 2026-10-10 — F4.1 concluída: Busca híbrida (HNSW + FTS, RRF, limiar), Reranker como Protocol, rota POST .../collections/{cid}/search; backend 966 testes, frontend 704.
- 2026-10-10 — F3.1 concluída: Workflow knobridge.ingestion.v1 (open_run/list_changes/process_batch/finish_run), run_items (migração 0011), cache de embedding por hash, start_sync/TemporalSyncStarter; fake de embeddings unificado com a F4.1; 1001 testes.
- 2026-10-10 — F3.2 e F4.2 iniciadas em paralelo.
- 2026-10-10 — F4.2 concluída: HybridRetriever no chat, assistant_collections + min_similarity (migração 0012), citações com caminho/linhas/commit, prompt reforçado; regra 8 preservada; backend 1031 testes.
- 2026-10-10 — F3.2 concluída: API de coleções, fontes (teste de conexão, sync, cancel), execuções e documentos; mesclada com a F4.2 (conflitos só em AGENTS.md; contrato regenerado); backend e frontend verdes.
- 2026-10-10 — F3.3 e F5.1 iniciadas em paralelo.
- 2026-10-10 — F5.1 concluída: Tela /w/:id/collections (lista, CRUD, detalhe com fontes e Testar busca); 759 testes.
- 2026-10-10 — F5.3 iniciada (em paralelo com a F3.3).

## 8. Encerramento

A preencher ao concluir.
