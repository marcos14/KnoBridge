# Avaliação das respostas

> Rascunho v0.1 · 2026-10-17 · Plano 0011 (F1.1; implementação na F4.1)

Contrato do **conjunto de avaliação sintético** do KnoBridge e do roteiro que o roda contra uma stack: o corpus, o formato das perguntas com gabarito, como uma resposta é julgada, as métricas, o relatório e a comparação entre duas execuções. Serve para medir o antes e o depois de cada mudança na qualidade das respostas (reranker, [busca em etapas](chat.md#busca-em-etapas), limiar por modelo, instruções dos níveis) sem dados de terceiros no repositório (regra 9 do [AGENTS.md](../../AGENTS.md)). A decisão está no [plano 0011](../planos/0011-qualidade-da-resposta.md) (D5) e no [ADR 0010](../adr/0010-busca-em-etapas-e-reranker.md).

Código previsto: `scripts/eval/` (F4.1), um pacote do projeto `knobridge-scripts`, rodado de dentro de `scripts/` com `uv run python -m eval`, com a dependência nova `httpx` (cliente HTTP e `MockTransport` dos testes), fixada no `uv.lock`. Guia de uso: `docs/guias/avaliar-respostas.md` (F4.2).

## Princípios

- **Sintético e pequeno.** Tudo no corpus é inventado para um ERP fictício, o **Vértice ERP** (o mesmo de `scripts/synthetic_tickets`). Nada de código, chamado ou documento real.
- **Sob demanda, contra a stack, com LLM real.** O roteiro não roda na CI com provedor real (avaliação automática na CI é da fase 3 da visão, D13). Na CI e nos testes, ele roda contra uma API falsa; contra a stack, roda também com o provedor `fake` de ponta a ponta, para provar o caminho.
- **Só a API pública do KnoBridge.** O roteiro prepara tudo pelas rotas do painel (sessão e CSRF) e pergunta pela REST própria da API pública ([api-publica.md](api-publica.md#rest-própria-de-conversa)), com `stream: false`. Nunca lê o banco.
- **O Minski fica fora.** As perguntas dos ensaios com dados reais ([0005](../pesquisa/0005-niveis-no-minski.md), [0006](../pesquisa/0006-mcp-e-widget-no-minski.md)) continuam fora do repositório e são usadas só nos ensaios (F4.3).

## Corpus

Em `scripts/eval/corpus/`, versionado, pequeno (a ordem de grandeza abaixo é um teto, não uma meta):

| Pasta ou arquivo | Fonte criada | Tipo e nível mínimo | Conteúdo |
|---|---|---|---|
| `manual/` | `eval-manual` | `folder`, `end_user` (padrão) | Até 15 artigos em Markdown do manual do usuário: telas, passo a passo, mensagens de erro, regras de negócio em linguagem simples. Nomes `manual-<assunto>.md`. |
| `interno/` | `eval-interno` | `folder`, `support` (explícito) | Até 6 documentos internos em Markdown: o **esquema do banco** (`interno-esquema-do-banco.md`, com as tabelas e colunas em blocos de código SQL dentro do Markdown, para não virar código e subir para `product_dev`), runbooks e validações. Nomes `interno-<assunto>.md`. |
| `codigo/` | `eval-codigo` | `folder`, `product_dev` (código detectado sobe para `product_dev` de qualquer forma) | Até 12 arquivos de código de exemplo em `src/` (TypeScript) e as migrações em `migrations/` (SQL), mais a pasta `gerado/` com 2 ou 3 arquivos JSON grandes e repetitivos, para exercitar o [aviso de arquivos que dominam o índice](indexacao.md#arquivos-que-dominam-o-índice). |
| `chamados.jsonl` | `eval-chamados` | `tickets`, `support` | Até 40 chamados no formato de [chamados.md](chamados.md), com dados pessoais fictícios (a anonimização roda). `external_id` `EVAL-T-<nnn>`. |
| `cards.jsonl` | `eval-cards` | `cards`, `product_dev` | Até 15 cards no formato de [cards.md](cards.md), alguns concluídos e outros em andamento. `external_id` `EVAL-C-<nnn>`. |

- Os nomes de arquivo são únicos no corpus inteiro, com o prefixo da pasta (`manual-`, `interno-`) ou o caminho (`src/`, `migrations/`, `gerado/`), para o gabarito identificar a fonte pela citação.
- As pastas de arquivos são lidas pelo worker da stack: a fonte de pasta exige um caminho dentro de `/sources`. O subcomando `copy-corpus` copia `manual/`, `interno/` e `codigo/` para uma pasta do host montada lá (por padrão `deploy/sources/eval/`, que o compose monta em `/sources/eval`).
- O corpus inclui de propósito: perguntas que só se respondem com uma segunda busca (a pergunta usa palavras de negócio e a resposta está num documento que usa o termo técnico), um chamado aberto e um resolvido do mesmo problema, um card concluído e um em andamento sobre o mesmo pedido, e conteúdo de `support` e `product_dev` que o `end_user` não pode receber.

## Perguntas e gabarito

Arquivo `scripts/eval/perguntas.json`, validado pelo roteiro antes de qualquer chamada (inválido: código de saída 2, com o caminho do erro):

```json
{
  "version": 1,
  "level_rules": {
    "end_user": {"forbidden": ["ticket:*", "card:*", "path:interno-*", "path:src/**", "path:migrations/**", "path:gerado/**"]},
    "support": {"forbidden": ["card:*", "path:src/**", "path:migrations/**", "path:gerado/**"]},
    "product_dev": {"forbidden": []}
  },
  "questions": [
    {
      "id": "su-03",
      "level": "support",
      "kind": "sql",
      "question": "Monte uma consulta para listar os clientes com limite de crédito estourado e quanto passaram do limite.",
      "answerable": true,
      "needs_steps": true,
      "expected_sources": {"any": ["path:interno-esquema-do-banco.md"], "all": []},
      "must_include": [["limite_credito", "limite de crédito"], ["select"]],
      "must_not_include": ["update ", "delete "]
    },
    {
      "id": "eu-09",
      "level": "end_user",
      "kind": "unrelated",
      "question": "Qual é a receita de feijoada?",
      "answerable": false
    }
  ]
}
```

| Campo | Regras |
|---|---|
| `version` | `1`. |
| `level_rules.<nível>.forbidden` | Matchers (abaixo) que uma resposta nesse nível **nunca** pode citar. Os três níveis são obrigatórios. |
| `id` | Único, `[a-z0-9-]`, até 40 caracteres. Convenção: `eu-`, `su-`, `pd-` + número. |
| `level` | `end_user`, `support` ou `product_dev`: a conversa é criada nesse nível. |
| `kind` | `how_to`, `business_rule`, `error_message`, `where_in_code`, `sql`, `validation`, `already_done`, `planning`, `ticket_history` ou `unrelated`. Só agrupa o relatório. |
| `question` | 1 a 2000 caracteres. |
| `answerable` | `true`: o corpus tem a resposta **neste nível**. `false`: a resposta certa é dizer que não sabe (sem relação com o corpus, ou a informação existe só acima do nível). |
| `needs_steps` | Opcional, padrão `false`: a pergunta foi escrita para precisar de uma segunda busca. O relatório mede o acerto nesse grupo à parte. |
| `expected_sources.any` | Com `answerable: true`, obrigatório e não vazio: a resposta precisa citar **ao menos um** destes matchers. |
| `expected_sources.all` | Opcional: a resposta precisa citar **todos** estes. |
| `must_include` | Opcional: lista de grupos; cada grupo é uma lista de alternativas, e o texto da resposta precisa conter **ao menos uma** alternativa de **cada** grupo. |
| `must_not_include` | Opcional: nenhum destes pode aparecer no texto. |

**Matchers** (contra cada citação da resposta, no formato de [chat-sse.md](chat-sse.md#citations)):

| Forma | Casa quando |
|---|---|
| `path:<glob>` | `citation.path` casa o glob (`*` dentro de um segmento, `**` em qualquer profundidade). Arquivos de pasta. |
| `ticket:<external_id ou *>` | `citation.kind == "ticket"` e `citation.uri == "ticket:<external_id>"` (ou qualquer chamado com `*`). |
| `card:<external_id ou *>` | `citation.kind == "card"` e `citation.uri == "card:<external_id>"` (ou qualquer card com `*`). |

**Texto normalizado** (para `must_include`, `must_not_include` e a detecção de "não sei"): minúsculas, sem acentos (NFKD sem marcas), espaços em sequência viram um. A busca é por substring.

## Execução

### Preparação (`run`, passo 1)

O roteiro precisa de um workspace em que o usuário informado seja owner ou admin, de preferência só para a avaliação (ele muda a configuração dos níveis e restaura no fim). Pelas rotas do painel:

1. Login (`POST /v1/auth/login`) e o cookie de CSRF.
2. Credencial de LLM (`POST .../providers`) com a chave de `KNOBRIDGE_EVAL_CHAT_KEY` (ou nenhuma chave para o `fake`) e, se o provedor de chat não tiver embeddings (Anthropic), uma segunda credencial para o embedding (`KNOBRIDGE_EVAL_EMBEDDING_KEY`).
3. Coleção `eval-<rótulo>` com o modelo de embedding pedido.
4. As cinco fontes do corpus nessa coleção (as de pasta apontando para `--sources-root`, padrão `/sources/eval`; `eval-interno` com `min_level: support`), o upload de `chamados.jsonl` e `cards.jsonl` pelas rotas de upload, a sincronização de cada fonte e a espera até todas terminarem com sucesso (consulta às execuções a cada 2 s, até `--index-timeout`, padrão 600 s).
5. Produto `eval-<rótulo>` ligado à coleção, com `rerank` conforme `--rerank` e `min_similarity` nulo (o padrão do modelo), salvo `--min-similarity`.
6. Leitura da configuração atual dos três níveis (para restaurar) e `PATCH` de cada nível com a credencial, o modelo (`--model <nível>=<modelo>`) e `max_steps` (`--max-steps <nível>=<n>`, padrão o do nível).
7. Chave de API `eval-<rótulo>` com o produto e `max_level: product_dev`.

### Perguntas (`run`, passo 2)

Para cada pergunta, na ordem do arquivo, e para cada repetição (`--repeat`, padrão 1): `POST /v1/conversations` com o produto e o nível da pergunta, `POST /v1/conversations/{id}/messages` com `stream: false`, e o registro do `PublicAnswerOut` (status, texto, citações, `steps`, `model`, tokens, `cost_usd`, `latency_ms`). Uma conversa por pergunta e repetição; sem paralelismo (o tempo medido é o de uma pergunta sozinha). Um erro HTTP vira `verdict: error`, com o código, e a execução segue.

### Encerramento (`run`, passo 3)

Restaura os três níveis como estavam (credencial, modelo, temperatura e `max_steps`; as instruções não são tocadas), revoga a chave e, com `--cleanup`, exclui o produto, as fontes, a coleção e as credenciais criadas. Sem `--cleanup`, deixa tudo para inspeção no painel. O encerramento roda mesmo depois de erro ou interrupção (`Ctrl+C`).

### Linha de comando

```bash
cd scripts
uv run python -m eval copy-corpus --to ../deploy/sources/eval
uv run python -m eval run --base-url http://localhost:8000 --email admin@exemplo.com.br \
  --workspace-id <uuid> --chat-provider openrouter --embedding-provider openrouter \
  --embedding-model openai/text-embedding-3-small \
  --model end_user=openai/gpt-4.1-mini --model support=anthropic/claude-sonnet-5.5 \
  --model product_dev=anthropic/claude-opus-5.5 --rerank on --label com-etapas \
  --out ../../kb-eval/2026-10-20-com-etapas
uv run python -m eval compare ../../kb-eval/A/report.json ../../kb-eval/B/report.json --out ../../kb-eval/A-x-B.md
```

| Opção | Padrão | Uso |
|---|---|---|
| `--base-url` | `http://localhost:8000` | API da stack. |
| `--email` | (obrigatório) | Usuário owner ou admin; a senha vem de `KNOBRIDGE_EVAL_PASSWORD`. |
| `--workspace-id` | (obrigatório) | Workspace da avaliação. |
| `--chat-provider`, `--embedding-provider` | `fake` | `fake`, `openai`, `anthropic` ou `openrouter`. As chaves vêm de `KNOBRIDGE_EVAL_CHAT_KEY` e `KNOBRIDGE_EVAL_EMBEDDING_KEY`, nunca da linha de comando. |
| `--embedding-model` | `fake-embedding` | Modelo da coleção. |
| `--model <nível>=<modelo>` | `fake-chat` nos três | Modelo de cada nível. |
| `--max-steps <nível>=<n>` | o valor atual do nível | 1 a 6. `1` em todos dá a linha de base sem etapas. |
| `--rerank` | `on` | `on` ou `off` (a opção do produto). |
| `--min-similarity` | nulo | Número de 0 a 1 para fixar o limiar do produto. |
| `--questions` | `eval/perguntas.json` | Outro arquivo de perguntas no mesmo formato (por exemplo, fora do repositório). |
| `--levels` | os três | Só as perguntas destes níveis (separados por vírgula). |
| `--repeat` | 1 | Repetições de cada pergunta (1 a 5). |
| `--sources-root` | `/sources/eval` | Onde a stack vê as pastas do corpus. |
| `--index-timeout` | 600 | Segundos de espera pela indexação. |
| `--label` | `run` | Rótulo dos recursos criados (`eval-<rótulo>`) e do relatório; `[a-z0-9-]`, até 30 caracteres. |
| `--cleanup` | desligado | Exclui o que criou. |
| `--out` | (obrigatório) | Pasta do relatório, criada se não existir; **fora do repositório** (o roteiro recusa um caminho dentro dele, código de saída 2). |

Códigos de saída: 0 terminou (mesmo com respostas erradas), 1 falha na preparação ou na indexação, 2 entrada inválida. As senhas e chaves nunca são escritas no relatório nem no stdout.

## Julgamento de uma resposta

Para cada resposta, nesta ordem:

1. **`said_unknown`**: `status == "no_source"`, ou o texto normalizado é igual à `no_source_message` normalizada do produto (o modelo respondeu a mensagem de sem fonte com fontes no contexto).
2. **`leaks`**: as citações que casam algum matcher de `level_rules[<nível>].forbidden`. Qualquer vazamento é grave: o filtro de nível no SQL não deveria permitir.
3. **`source_hit`**: alguma citação casa `expected_sources.any` e todas as de `expected_sources.all` são citadas.
4. **`include_ok`**: cada grupo de `must_include` tem uma alternativa no texto normalizado; **`exclude_ok`**: nenhum item de `must_not_include` aparece.

| `verdict` | Quando |
|---|---|
| `error` | A chamada falhou (HTTP de erro) ou `status` é `failed` ou `interrupted`. |
| `leak` | `leaks` não vazio (vale acima de qualquer outro, menos `error`). |
| `correct` | `answerable` e `status == "completed"` e não `said_unknown` e `source_hit` e `include_ok` e `exclude_ok`; ou não `answerable` e `said_unknown`. |
| `unknown` | `answerable` e `said_unknown`: disse que não sabe quando havia resposta. |
| `wrong` | Os demais: respondeu com fonte errada, sem o conteúdo obrigatório, com conteúdo proibido, ou respondeu uma pergunta sem resposta (alucinação). |

O julgamento é mecânico e conservador: ele mede se a resposta citou a fonte certa e contém os termos-chave, não se está bem escrita. A leitura humana de uma amostra continua no ensaio (F4.3).

## Métricas

Por nível e no total (e, dentro de cada um, só as perguntas `needs_steps`):

| Métrica | Definição |
|---|---|
| `questions` | Respostas avaliadas (perguntas × repetições). |
| `correct`, `unknown`, `wrong`, `leak`, `error` | Contagem de cada `verdict`. |
| `accuracy` | `correct / questions` (4 casas). |
| `source_recall` | Entre as respostas de perguntas `answerable`, a fração com `source_hit`. |
| `unknown_rate` | Entre as respostas de perguntas `answerable`, a fração com `said_unknown`. |
| `hallucination_rate` | Entre as respostas de perguntas não `answerable`, a fração sem `said_unknown`. |
| `steps_mean`, `steps_max` | Média e máximo de `steps`. |
| `multi_step_rate` | Fração das respostas com `steps > 1`. |
| `cost_usd_total`, `cost_usd_mean` | Soma e média dos `cost_usd` conhecidos; `unpriced` = respostas com custo nulo. |
| `input_tokens_mean`, `output_tokens_mean` | Médias dos conhecidos. |
| `latency_ms_p50`, `latency_ms_p95` | Percentis de `latency_ms` (método do vizinho mais próximo, sobre os valores ordenados). |

## Relatório

O `run` grava duas saídas em `--out`:

### `report.json`

```json
{
  "version": 1,
  "label": "com-etapas",
  "started_at": "2026-10-20T14:00:00Z",
  "finished_at": "2026-10-20T14:21:13Z",
  "config": {
    "base_url_host": "localhost:8000",
    "questions_file": "eval/perguntas.json",
    "questions_sha256": "…",
    "embedding_model": "openai/text-embedding-3-small",
    "rerank": true,
    "rerank_available": true,
    "min_similarity": null,
    "effective_min_similarity": [{"embedding_model": "openai/text-embedding-3-small", "value": 0.35, "source": "model"}],
    "levels": {
      "end_user": {"model": "openai/gpt-4.1-mini", "max_steps": 2},
      "support": {"model": "anthropic/claude-sonnet-5.5", "max_steps": 3},
      "product_dev": {"model": "anthropic/claude-opus-5.5", "max_steps": 4}
    },
    "repeat": 1
  },
  "index": {
    "sources": [{"name": "eval-codigo", "kind": "folder", "documents": 15, "chunks": 210, "dominant": [{"kind": "directory", "pattern": "gerado/**", "share": 0.41}]}]
  },
  "summary": {
    "total": {"questions": 30, "correct": 24, "unknown": 3, "wrong": 3, "leak": 0, "error": 0, "accuracy": 0.8, "…": "…"},
    "by_level": {"end_user": {"…": "…"}, "support": {"…": "…"}, "product_dev": {"…": "…"}},
    "needs_steps": {"total": {"…": "…"}, "by_level": {"…": "…"}}
  },
  "answers": [
    {
      "question_id": "su-03", "repeat": 1, "level": "support", "kind": "sql", "verdict": "correct",
      "status": "completed", "said_unknown": false, "source_hit": true, "include_ok": true, "exclude_ok": true,
      "leaks": [], "steps": 2, "model": "anthropic/claude-sonnet-5.5",
      "input_tokens": 9120, "output_tokens": 640, "cost_usd": 0.024640, "latency_ms": 11840,
      "citations": [{"index": 1, "kind": "file", "uri": "interno-esquema-do-banco.md#L1-L40"}],
      "answer": "…",
      "conversation_id": "…", "message_id": "…", "error_code": null
    }
  ]
}
```

- `answer` traz o texto inteiro (o corpus é sintético). Com `--questions` de fora do repositório (dados reais num ensaio), `--redact-answers` grava `answer: null` e as citações só com `index` e `kind`.
- `base_url_host` é só host e porta; nenhuma credencial, e-mail, chave ou id de credencial vai para o relatório.
- `index.sources` vem de `GET .../sources` (com `index_stats`, [indexacao.md](indexacao.md#arquivos-que-dominam-o-índice)).

### `report.md`

Em pt-BR, para ler e colar num relatório de ensaio:

1. Cabeçalho com o rótulo, as datas e a configuração (modelos e `max_steps` por nível, reranker, modelo de embedding e limiar efetivo).
2. Tabela de resumo por nível e total: respostas, corretas, "não sei", erradas, vazamentos, erros, acerto, `source_recall`, média de etapas, custo total e médio, latência p50 e p95.
3. A mesma tabela só para as perguntas `needs_steps`.
4. O índice: fontes, documentos, trechos e os avisos de arquivos dominantes.
5. Uma linha por resposta: id, nível, veredito, etapas, custo, latência e as citações (uris), sem o texto.
6. As respostas não corretas, com a pergunta e os primeiros 300 caracteres da resposta (omitidos com `--redact-answers`).

## Comparação

`compare A.json B.json --out <arquivo.md>` lê dois relatórios do mesmo arquivo de perguntas (`questions_sha256` igual; diferente: aviso no topo, compara só os ids em comum) e escreve, em Markdown:

- as configurações lado a lado (só o que difere);
- o resumo por nível com as duas colunas e a diferença (acerto, `source_recall`, "não sei", vazamentos, etapas médias, custo médio, latência p50);
- as perguntas que mudaram de veredito (de `correct` para outro e o contrário), com as etapas e o custo nas duas execuções.

Com `--repeat` maior que 1, a comparação usa a fração de acertos de cada pergunta.

## Testes

Da F4.1, com 95% de cobertura de linhas e branches no projeto `scripts/`:

- validação do `perguntas.json` (cada campo e cada matcher);
- matchers e normalização de texto;
- julgamento: uma tabela de casos para cada veredito, inclusive o "não sei" pelo texto e o vazamento;
- métricas e percentis com valores conhecidos;
- o roteiro inteiro contra uma API falsa (`httpx.MockTransport` com as rotas usadas, respostas sintéticas, inclusive erro HTTP no meio e restauração dos níveis no encerramento);
- `report.json`, `report.md` e `compare` comparados com arquivos esperados;
- recusa de `--out` dentro do repositório e de chave na linha de comando;
- um teste `repo` que valida o `perguntas.json` e o corpus versionados (ids únicos, matchers que existem no corpus, JSONL válido nos formatos de chamado e card).

Nenhum teste chama a stack, um LLM ou embeddings. A execução com o provedor `fake` contra a stack é feita pelo orquestrador na F4.1 e documentada no guia.

## Referências

- [plano 0011](../planos/0011-qualidade-da-resposta.md) (D5) e [ADR 0010](../adr/0010-busca-em-etapas-e-reranker.md).
- Visão, seção 7.8 (avaliação na fase 3): [01-visao-do-projeto.md](../01-visao-do-projeto.md#78-observabilidade-e-avaliação).
- `httpx.MockTransport`: <https://www.python-httpx.org/advanced/transports/#mock-transports>
