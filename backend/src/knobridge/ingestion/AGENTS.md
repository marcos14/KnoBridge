# backend/src/knobridge/ingestion/

**Função**: o conhecimento indexado do workspace e, a partir das próximas subfases, a ingestão que o preenche (parsing, chunking e orquestração incremental, conforme o layout de [backend/AGENTS.md](../../../AGENTS.md)). Hoje, só o modelo de dados do índice ([ADR 0004](../../../../docs/adr/0004-indice-de-conhecimento.md)).

**Entra aqui**:
- `models.py`: `Collection` (credencial e modelo de embedding, dimensão fixa `EMBEDDING_DIMENSION` = 1536), `Source` (coleção, `kind`, `config` JSON, `include_globs`/`exclude_globs`, `schedule_cron`/`schedule_enabled`, `cursor`, `active`; `typed_config()`), `Run` (gatilho, status, contagens, tokens, custo, início/fim, erro resumido), `RunError` (documento que falhou numa execução: chave, etapa, código, mensagem curta), `Document` (chave natural única por fonte, `kind` `file`/`commit`, hash do conteúdo) e `Chunk` (ordem, conteúdo, `meta`, hash, modelo de embedding, `embedding vector(1536)` e `tsv` gerado), com os enums `RunTrigger`, `RunStatus`, `RunErrorStage` e `DocumentKind`. Seis tabelas com RLS forçada (política padrão de workspace).
- `source_config.py`: `SourceKind` (`git`, `folder`) e a configuração por tipo em Pydantic: `GitSourceConfig` (exatamente um entre `path` local absoluto e `url` https pública sem credenciais; `branch` opcional, `None` = branch padrão; `initial_commit_limit` de 0 a 5000) e `FolderSourceConfig` (`path` absoluto), ambos com `extra="forbid"`; `parse_source_config(kind, data)` valida na fronteira (API, worker).
- Depois: parsing, chunking, a lógica incremental por hash de documento e cursor por fonte, e as funções que as activities de `workers/` chamam.

**Não entra aqui**: conectores (`connectors/`, um subpacote por conector), busca e montagem de contexto (`retrieval/`), workflows e activities do Temporal (`workers/`), adaptadores de embedding (`llm/`), routers e schemas (`api/`), migrações (`backend/migrations/`).

**Convenções locais**:
- O modelo `Source` mora aqui, e não num pacote `sources/` à parte, porque a configuração, os globs e o cursor só têm sentido para a ingestão que os consome; o registro de conectores fica em `connectors/`.
- Globs são colunas de `sources`, não parte de `config`: valem para todo tipo de fonte, são aplicados pelo motor de ingestão (não pelo conector) e a API e o painel os editam à parte.
- O banco só garante que `config` é um objeto JSON; o formato é validado por `parse_source_config`. Grave `config.model_dump(mode="json")`.
- Toda referência entre as tabelas é composta, `(workspace_id, <pai>_id)`. `NO ACTION` de coleção para credencial e de fonte para coleção (em uso não se exclui); `CASCADE` da fonte para execuções, erros, documentos e chunks.
- `chunks.collection_id` é desnormalizado da fonte do documento, para a busca filtrar sem junção; quem grava o chunk usa a coleção da fonte. Cada chunk registra `embedding_model`: trocar o modelo da coleção exige reindexar.
- Toda consulta filtra por `workspace_id` e roda no escopo de RLS do workspace ([ADR 0001](../../../../docs/adr/0001-tenancy-e-rls.md)). Mudou modelo: migração nova e [modelo de dados](../../../../docs/specs/modelo-de-dados.md) na mesma entrega.

**Como testar**: de `backend/`, `uv run pytest tests/ingestion` (os de RLS usam Postgres real; exige Docker). Gate da suíte inteira: `uv run pytest`.

**Leia também**: [ADR 0004](../../../../docs/adr/0004-indice-de-conhecimento.md); seção 7.3 da [visão](../../../../docs/01-visao-do-projeto.md); [llm/AGENTS.md](../llm/AGENTS.md); [tests/ingestion/AGENTS.md](../../../tests/ingestion/AGENTS.md).
