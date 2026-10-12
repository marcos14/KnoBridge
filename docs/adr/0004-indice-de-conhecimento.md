# ADR 0004 — Índice de conhecimento

> Status: aceito · 2026-10-10 · plano 0003 (F1.1)

## Contexto

O plano 0003 leva o primeiro conhecimento de ponta a ponta: fontes Git e pastas locais viram documentos e chunks indexados, que o chat consulta com citações. A [visão](../01-visao-do-projeto.md) já fixa o banco vetorial padrão (D3: pgvector, extensão habilitada desde a migração `0001`), a orquestração (D4: Temporal, com lógica incremental própria) e os embeddings por API (D5: OpenAI ou Gemini, reindexação ao trocar). A seção 7.3 pede índice denso (HNSW) mais lexical (`tsvector`) com metadados e o registro de qual modelo gerou cada vetor.

Faltava decidir como coleção, fonte e modelo de embedding se relacionam, se a dimensão do vetor é fixa ou varia por coleção, onde mora a configuração de cada tipo de fonte e como o pipeline roda antes do canvas visual (seção 7.2), que ainda não existe. As decisões D9 e D10 do [plano 0003](../planos/0003-primeiro-conhecimento.md) registram a escolha; este ADR é a referência de arquitetura.

## Decisão

1. **A coleção define o embedding.** `collections` guarda a credencial de provedor (FK composta `(workspace_id, credential_id)`, mesmo workspace, `NO ACTION` na exclusão), o modelo de embedding e a dimensão. Todo chunk da coleção é gerado com esse modelo.
2. **Uma fonte pertence a uma única coleção** (`sources.collection_id`, `NO ACTION`: coleção com fontes não se exclui). Um assistente consultará N coleções (ligação em subfase posterior). O mesmo documento nunca é indexado com dois modelos, e o incremental fica por fonte.
3. **Dimensão fixa de 1536** em `chunks.embedding vector(1536)`, com um único índice HNSW `vector_cosine_ops`. `collections.embedding_dimension` existe para deixar o valor explícito na API, mas um `CHECK` o prende a 1536. Modelos com vetor nativo maior (ex.: `text-embedding-3-large`, Gemini Embedding) são usados com a dimensão de saída reduzida (Matryoshka / parâmetro `dimensions`).
4. **Cada chunk registra o modelo** que gerou o vetor (`chunks.embedding_model`). Trocar o modelo de uma coleção exige reindexar as fontes dela; até lá, chunks de modelo diferente do da coleção são identificáveis e a busca não mistura espaços vetoriais.
5. **Índice lexical gerado pelo banco**: `chunks.tsv` é `GENERATED ALWAYS AS ... STORED`, com `to_tsvector('portuguese', content)` (stemming em pt-BR) concatenado a `to_tsvector('simple', ...)` sobre o caminho (inteiro e quebrado em `/` e `.`) e o símbolo dos metadados (identificadores casam como escritos). Índice GIN. Nenhum código de aplicação mantém o `tsvector`.
6. **Configuração por tipo em JSON validado na fronteira**: `sources.config` é `jsonb` (o banco só exige um objeto); o formato depende de `sources.kind` (`git`, `folder`) e é validado por modelos Pydantic (`GitSourceConfig`, `FolderSourceConfig`) em `backend/src/knobridge/ingestion/source_config.py`. Globs de inclusão e exclusão são colunas (`text[]`), comuns a todos os tipos e aplicados pelo motor de ingestão, não pelo conector.
7. **Pipeline fixo sobre Temporal, sem canvas neste bloco**: a ingestão é um workflow Temporal com activities idempotentes; a lógica incremental é própria, por hash do conteúdo do documento (`documents.content_hash`, chave natural única por fonte) e cursor por fonte (`sources.cursor`). O canvas da seção 7.2 reaproveitará as mesmas activities depois.
8. **Execuções e erros por documento** ficam em `runs` (gatilho, status, contagens, tokens, custo, erro resumido) e `run_errors` (documento, etapa, código, mensagem curta): um documento com erro não derruba a execução.
9. **Tenancy**: as seis tabelas (`collections`, `sources`, `runs`, `run_errors`, `documents`, `chunks`) têm `workspace_id NOT NULL`, RLS forçada com a política padrão ([ADR 0001](0001-tenancy-e-rls.md)) e referências compostas `(workspace_id, <pai>_id)`. `chunks.collection_id` é desnormalizado da fonte para a busca filtrar sem junção.

## Alternativas consideradas

- **Fonte em várias coleções (N:N), com reindexação por coleção**: permite o mesmo repositório em coleções com modelos diferentes, mas duplica documentos e chunks, multiplica o custo de embedding e complica o incremental (um cursor por par fonte × coleção). Descartada nesta fase; a mesma fonte pode ser cadastrada duas vezes se for preciso.
- **Dimensão variável por coleção**: exigiria coluna `vector` sem dimensão (sem índice HNSW, que pede dimensão fixa), uma tabela ou partição por dimensão, ou índices parciais por coleção. Mais flexível, mas multiplica índices e consultas. Descartada; 1536 cobre os modelos de API priorizados em D5.
- **`halfvec` ou dimensão menor (768)**: economiza espaço, mas perde qualidade e diverge do padrão dos modelos OpenAI. Fica como otimização futura, medida.
- **Canvas visual já neste bloco**: atrasaria o primeiro conhecimento útil; o canvas entra depois sobre as mesmas activities.
- **CocoIndex como motor incremental**: D4 o deixa só como biblioteca opcional; a lógica incremental própria por hash e cursor é pequena e fica sob nosso controle de tenancy e auditoria.
- **`tsvector` mantido pela aplicação ou por trigger**: mais código e risco de divergir do conteúdo. A coluna gerada é imutável e sempre coerente.
- **Globs dentro de `config`**: obrigaria cada modelo de configuração a repeti-los e cada conector a aplicá-los. Descartada.

## Consequências

- Trocar o modelo de embedding de uma coleção é uma operação de reindexação (custo e tempo proporcionais ao conteúdo); a interface deve deixar isso explícito.
- Um modelo de embedding sem saída em 1536 dimensões não pode ser usado sem um novo ADR (mudar a coluna e reindexar tudo).
- Excluir uma credencial de embedding em uso falha (409 `provider_in_use`), como acontece com assistentes; excluir uma coleção exige excluir antes as fontes dela; excluir uma fonte apaga execuções, documentos e chunks dela; excluir o workspace apaga tudo.
- O `CHECK` de dimensão e o `vector(1536)` garantem no banco o que a aplicação promete; o formato de `config` só é garantido pela validação Pydantic, então toda escrita passa por `parse_source_config`.
- A migração `0010` cria as tabelas; modelo de dados em [docs/specs/modelo-de-dados.md](../specs/modelo-de-dados.md).
