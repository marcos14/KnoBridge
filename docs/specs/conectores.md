# Conectores

> Rascunho v0.1 · 2026-10-11 · Em uso (plano 0003)

Como o KnoBridge lê documentos das fontes: o contrato que todo conector implementa, as regras de seleção de arquivos compartilhadas pelos conectores de árvore e o comportamento dos dois conectores existentes, **pasta local** e **Git**. O que acontece depois da leitura (parsing, chunking, embeddings, execução e busca) está em [indexacao.md](indexacao.md); as tabelas, em [modelo-de-dados.md](modelo-de-dados.md#índice-de-conhecimento); as decisões de arquitetura, no [ADR 0004](../adr/0004-indice-de-conhecimento.md).

Código: [`backend/src/knobridge/connectors/`](../../backend/src/knobridge/connectors/AGENTS.md) (contrato e seleção), [`connectors/folder/`](../../backend/src/knobridge/connectors/folder/AGENTS.md) e [`connectors/git/`](../../backend/src/knobridge/connectors/git/AGENTS.md). Configuração das fontes: `backend/src/knobridge/ingestion/source_config.py`. Testes: [`backend/tests/connectors/`](../../backend/tests/connectors/AGENTS.md).

## Contrato

Um conector lê **uma** fonte e nunca toca no banco. O motor de ingestão guarda o cursor em `sources.cursor` e grava os documentos pela chave natural. Interface (`connectors/base.py`, todos os métodos são `async`):

| Método | O que faz |
|---|---|
| `list_changes(cursor) -> ChangeSet` | Compara a fonte com o cursor da última execução bem-sucedida (`None` na primeira) e devolve o que foi adicionado, alterado e removido, mais o cursor novo. |
| `fetch(ref) -> RawDocument` | Lê um documento. O que a listagem não listaria (sumiu, ignorado, binário, grande demais, fora da branch) é `DocumentNotFoundError`. |
| `permissions(ref) -> Acl` | Quem pode ver o documento. Pasta e Git devolvem `OPEN_ACL` (todo membro do workspace); ACL por documento fica para conectores que a tenham. |
| `test_connection()` | Retorna se a fonte é legível; senão levanta um `ConnectorError`. A API envolve a chamada num timeout de 30 s (`source_timeout`). |

Valores trocados:

| Tipo | Campos |
|---|---|
| `DocumentRef` | `key` (chave natural, única por fonte e estável entre execuções: caminho POSIX relativo à raiz para arquivos, `commit:<sha>` para commits) e `kind` (`file` ou `commit`). |
| `ChangeSet` | `added`, `changed`, `removed` (cada tupla ordenada pela chave) e `cursor`. `is_empty` quando nada mudou. |
| `RawDocument` | `ref`, `title`, `uri`, `content` (bytes), `extension` (minúscula, sem ponto), `language` (pela extensão, quando conhecida) e `metadata` (JSON). Derivados: `content_hash` (SHA-256 hex do conteúdo, que o motor usa para pular documento sem mudança) e `text` (UTF-8 tolerante). |
| `Acl` | `public` (padrão `true`) e `principals`. |
| `Cursor` | Objeto JSON opaco para o motor (guardado como JSONB), com `kind` e `version`. Todo conector recusa cursor que não é dele, ou de outra versão, com `InvalidCursorError`. |

Erros (`connectors/errors.py`), no formato único da API. As mensagens nunca levam conteúdo de arquivo, e os caminhos são relativos à raiz da fonte sempre que possível:

| Código | HTTP | Quando |
|---|---|---|
| `connector_error` | 502 | Classe base. |
| `source_unavailable` | 502 | A fonte não pode ser lida (pasta ausente, não é pasta, sem permissão, não é repositório Git, `git` falhou ou estourou o tempo). Na ingestão, é o único erro de conector que se repete com retry. |
| `path_outside_root` | 422 | Caminho fora da raiz permitida, direto, por `..`, por symlink ou por junção do Windows. |
| `document_not_found` | 404 | A referência não aponta para um documento selecionável. |
| `branch_not_found` | 422 | O repositório é legível, mas a branch configurada não existe (ou a branch padrão não tem commits). |
| `invalid_cursor` | 500 | O cursor guardado não foi produzido por este conector nem por esta versão dele. |

## Configuração das fontes

A configuração fica em `sources.config` (JSON) e depende de `sources.kind`; é validada por Pydantic na fronteira (`parse_source_config`, 422 `source_config_invalid`), com `extra="forbid"`:

| Tipo | Campos |
|---|---|
| `folder` | `path`: caminho absoluto no servidor. |
| `git` | Exatamente um entre `path` (caminho absoluto de um clone no servidor) e `url` (`https` pública, sem usuário nem senha); `branch` opcional (em branco = branch padrão; nomes que pareçam opção ou faixa de revisões são recusados); `initial_commit_limit` de 0 a 5000 (padrão 200). |

Os globs de inclusão e exclusão **não** fazem parte da configuração: são colunas da fonte (`include_globs`, `exclude_globs`, até 100 padrões cada), valem para qualquer tipo e são repassados ao conector por quem o monta (`ingestion/connectors.py`, `SettingsConnectorFactory`).

## Seleção de arquivos

Pasta e Git usam as mesmas regras (`connectors/selection.py`). Um arquivo entra quando passa por todas, nesta ordem:

1. **Raiz permitida.** A raiz da fonte é resolvida com `Path.resolve()` (seguindo symlinks) e tem de ser uma pasta existente dentro de `KNOBRIDGE_LOCAL_SOURCES_ROOT` (padrão `/sources`, onde o Docker Compose monta a pasta do host somente leitura). Fora dela: `path_outside_root`. Pasta ausente: `source_unavailable`.
2. **Diretórios padrão.** `.git`, `node_modules`, `dist`, `build` e `vendor` nunca são percorridos.
3. **`.gitignore` aninhado.** Cada pasta pode ter o seu; o mais profundo decide primeiro (como no git), com semântica gitwildmatch (biblioteca `pathspec`). Diretório ignorado não é percorrido.
4. **Lockfiles e binários conhecidos.** `package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `uv.lock`, `poetry.lock`, `Cargo.lock`, `go.sum` e outros (`LOCKFILE_NAMES`), e extensões binárias conhecidas (`BINARY_EXTENSIONS`: arquivos compactados, executáveis, bibliotecas, imagens, áudio, vídeo e fontes) ficam de fora sem que o arquivo seja aberto.
5. **Globs da fonte.** Inclusão vazia = todos os arquivos. Os padrões seguem a sintaxe do `.gitignore`, relativos à raiz: `*.md` casa em qualquer nível, `docs/**` só na raiz. Um arquivo que casa com algum padrão de exclusão sai.
6. **Tamanho.** Acima de `KNOBRIDGE_MAX_SOURCE_FILE_BYTES` (padrão 2 MiB) o arquivo é ignorado.
7. **Byte NUL.** Arquivo com byte NUL nos primeiros 8 KiB é binário e sai. Essa checagem precisa dos bytes, então acontece só na leitura, nunca na listagem de caminhos.

**Documentos parseáveis.** PDF, DOCX, XLSX e PPTX (`DOCUMENT_EXTENSIONS`) são binários, mas o parsing sabe convertê-los: pulam a checagem de NUL, têm limite próprio (`KNOBRIDGE_MAX_SOURCE_DOCUMENT_BYTES`, padrão 20 MiB) e chegam ao parser como bytes, com `metadata.format = "document"` (os demais, `"text"`). Formato novo só entra na lista quando o parsing souber convertê-lo.

**Symlinks e junções.** Symlink de arquivo cuja resolução fica dentro da raiz é seguido (a chave é o caminho do link); o que aponta para fora é ignorado. Symlink e junção de diretório nunca são seguidos, o que evita ciclos e duplicatas. Symlinks quebrados, sockets e FIFOs são ignorados; subpasta sem permissão de leitura é pulada sem derrubar a fonte.

**Chaves no `fetch`.** A chave é revalidada pelas mesmas regras. Chave absoluta, com `..`, `\`, letra de drive ou parte vazia é `path_outside_root`; caminho que passa por diretório-link ou que a listagem não listaria é `document_not_found`.

## Conector de pasta

Cada arquivo selecionado vira um documento `file` (`connectors/folder/`). A detecção de mudanças é por hash do conteúdo.

- **Cursor** (`FolderCursor`): `{"kind": "folder", "version": 1, "entries": {"<caminho>": ["<hash>", <tamanho>, <mtime_ns>]}}`. O hash guardado são os 32 primeiros caracteres hex (128 bits) do SHA-256 do conteúdo: colisão desprezível para detectar mudança, e o cursor de uma pasta com 10 mil arquivos fica em torno de 1 MB. O hash completo do documento vem de `RawDocument.content_hash` no `fetch`.
- **Atalho por mtime.** Com tamanho e mtime iguais aos do cursor, o hash anterior é reaproveitado sem ler o arquivo. Mudar só o mtime (ex.: `touch`) atualiza o cursor sem gerar mudança.
- **Listagem.** `added` = chaves novas; `removed` = chaves que sumiram ou deixaram de ser selecionadas (por `.gitignore`, glob ou tamanho); `changed` = chaves cujo hash mudou.
- **Raiz resolvida a cada chamada**: a pasta pode sumir, aparecer ou ser religada entre execuções.
- **Documento.** `title` = nome do arquivo; `uri` = `file://` do caminho no servidor (a citação usa o caminho relativo, não esta URI); `metadata` com `path`, `size_bytes` e `format`. Só aceita `DocumentKind.FILE`.
- IO bloqueante roda em `asyncio.to_thread`.

## Conector Git

Os arquivos do HEAD de uma branch, com a mesma seleção, mais os commits como documentos, sempre pelo binário `git` em subprocesso (`connectors/git/`).

### Leitura pelos objetos do Git

O conteúdo vem sempre dos objetos (`ls-tree` + `cat-file`), nunca do worktree:

- o clone local é lido no lugar e nunca alterado (nada de `fetch`, `checkout` ou escrita): a montagem pode ser somente leitura;
- mudanças não commitadas não vazam para o índice;
- repositório bare funciona.

O `path` tem de ser a **raiz** do repositório (uma subpasta faria o git usar o repositório que a contém) e, num worktree ligado, o `git-common-dir` também tem de estar dentro da raiz permitida.

**Execução do `git`** (`runner.py`): `asyncio.create_subprocess_exec`, sem shell, com timeout (padrão 600 s) e o processo morto ao estourar. Toda chamada leva:

- `-c safe.directory=<repositório>`: a montagem costuma ter outro dono que o usuário do worker, e o git recusaria o repositório. A opção vale só para aquele caminho, num escopo que o git respeita;
- `core.fsmonitor=false`, `--no-ext-diff` e `--no-textconv` nas comparações: uma configuração hostil no repositório não executa comandos enquanto só lemos;
- `--literal-pathspecs`;
- `GIT_OPTIONAL_LOCKS=0` (leitura não escreve no repositório) e `GIT_TERMINAL_PROMPT=0` (nunca pede credencial).

O stderr do git vai para o log (até 300 caracteres) e nunca para os `details` do erro, porque cita caminhos do worker e URLs.

### Repositório por URL

Uma `url` https é clonada uma vez em `KNOBRIDGE_GIT_WORKDIR/<sha256(url)[:24]>` (no Compose, o volume `source-clones`, só no worker):

- clone parcial (`--filter=blob:none --no-checkout --no-tags`): histórico completo de commits e árvores, conteúdo dos arquivos sob demanda;
- antes de cada listagem, `fetch --prune --force` e `checkout --detach` do HEAD, que baixa num lote só os conteúdos que faltam;
- só `https` é aceito (`protocol.allow=never` + `protocol.https.allow=always`), então um redirecionamento não troca de transporte. Os testes injetam `file://` por `allowed_protocols` e `url_rewriter`;
- clone pela metade (worker morto no meio) é apagado e refeito;
- `test_connection` usa `ls-remote` sem clonar, por isso funciona também na API, que não tem o volume de clones.

Repositório privado (com credencial cifrada) ainda não existe: URL com usuário ou senha é recusada.

### Branch

| Branch configurada | Local (`path`) | URL |
|---|---|---|
| Em branco | `HEAD` | `refs/remotes/origin/HEAD` |
| `<b>` | `refs/heads/<b>`, senão `refs/remotes/origin/<b>` (um clone montado costuma ter só a branch padrão local) | `refs/remotes/origin/<b>` |

Branch inexistente: `branch_not_found` (422).

### Seleção no Git

`ls-tree -r --long` dá caminho e tamanho de cada blob do HEAD. As regras são as da seção [Seleção de arquivos](#seleção-de-arquivos), com duas diferenças: os `.gitignore` vêm da **árvore do commit** e se aplicam até a arquivo rastreado, e só arquivos comuns e executáveis entram (symlinks e submódulos ficam de fora). Só os blobs novos ou alterados são lidos para a checagem de NUL, em lotes de cerca de 32 MiB; um caminho inalterado que já estava selecionado continua selecionado sem leitura.

### Incremental por SHA

Cursor (`GitCursor`): `{"kind": "git", "version": 1, "head": "<sha>", "commit": "<sha>", "paths": ["..."]}`.

- `head`: o commit cuja árvore foi indexada;
- `commit`: o commit mais novo cujo histórico já virou documentos;
- `paths`: as chaves selecionadas em `head`.

`paths` serve para saber o que remover quando o SHA do cursor sumiu (force-push seguido de `gc`) e para manter a seleção certa quando `.gitignore` ou globs mudam sem o arquivo mudar.

Na listagem:

1. **Com o `head` do cursor presente**, os arquivos tocados vêm de `git diff --name-status --no-renames <head do cursor> <head>`. Renomeação = chave antiga em `removed` + chave nova em `added`; detecção de renomeação não ajuda o índice e exigiria ler blobs. `changed` = chaves selecionadas antes e agora que o diff tocou.
2. **Sem o `head`** (histórico reescrito), **reconstrução**: tudo que está em `paths` e continua selecionado vai para `changed` (o motor pula pelo hash o que não mudou de fato), o resto para `added`/`removed`.
3. Seleção nova contra `paths` antigos: chaves que deixaram de ser selecionadas vão para `removed`, mesmo sem o arquivo mudar.

### Commits como documentos

- Chave e URI `commit:<sha>`, `DocumentKind.COMMIT`, sempre em `added` (um commit nunca muda).
- Na primeira sincronização, ou quando o `commit` do cursor sumiu, só os `initial_commit_limit` mais recentes (`rev-list --max-count`); depois, todos os novos desde o `commit` do cursor (`rev-list <head> ^<commit>`).
- Conteúdo (`commits.py`): só a mensagem completa (assunto e corpo, com uma quebra de linha no fim). SHA, autor, data e arquivos ficam nos metadados, e `render_commit` monta o Markdown a partir deles ([indexacao.md](indexacao.md#parsing)); repeti-los no conteúdo duplicaria a lista no trecho embedado. O hash do conteúdo é o SHA-256 da mensagem: estável e determinístico, porque um commit nunca muda, e a chave `commit:<sha>` já distingue commits com a mesma mensagem.
- `title` = primeira linha da mensagem (até 200 caracteres; vazia, `commit <sha12>`).
- `metadata`: `sha`, `parents`, `author`, `authored_at`, `committed_at`, `files` (`status`, `path`, `old_path`; `diff-tree -M`, com renomeações; merge comparado ao primeiro pai; até 500 arquivos), `files_total` (quantos arquivos o commit tocou, mesmo acima de 500) e `format: "text"`.
- **Sem e-mail.** E-mail do autor e o committer ficam de fora (LGPD, minimização): o nome basta para citar e responder "quem mudou isto".
- `fetch` de um commit que não é ancestral do HEAD da branch é `document_not_found`.

### Documento de arquivo

`title` = nome do arquivo; `uri` = caminho POSIX relativo; `metadata` com `path`, `commit` (o HEAD lido), `size_bytes` e `format`.

## Suíte de contrato

Todo conector passa pela mesma suíte (`backend/tests/connectors/contract/`), parametrizada por fonte. Hoje roda contra:

- um conector fake em memória;
- uma pasta em `tmp_path`;
- um repositório Git local em que cada mutação é um commit com data fixa;
- o mesmo repositório clonado por uma URL https reescrita para `file://`.

| Teste | Garante |
|---|---|
| `test_contract_first_listing_adds_every_document` | A primeira listagem (`cursor=None`) põe tudo em `added`. |
| `test_contract_listing_with_own_cursor_is_empty` | Listar de novo com o cursor devolvido não muda nada, inclusive depois de o cursor ir e voltar como JSON. |
| `test_contract_lists_added_changed_and_removed` | Adicionado, alterado e removido aparecem cada um na sua lista. |
| `test_contract_fetch_returns_content_and_sha256` | `fetch` devolve o conteúdo e o SHA-256 dele. |
| `test_contract_fetch_unknown_ref_raises_not_found`, `test_contract_fetch_removed_ref_raises_not_found` | Referência desconhecida ou removida dá `DocumentNotFoundError`. |
| `test_contract_permissions_are_open` | Pasta e Git devolvem ACL aberta. |
| `test_contract_test_connection_succeeds_on_readable_source`, `test_contract_test_connection_fails_on_broken_source` | `test_connection` passa na fonte legível e falha com `ConnectorError` na quebrada. |
| `test_contract_rejects_foreign_cursor` | Cursor de outro conector dá `InvalidCursorError`. |

As asserções olham só os documentos `file`: documentos de outro tipo, como os commits do Git, podem aparecer na listagem sem quebrar o contrato. Testes específicos de cada conector (renomeação, `.gitignore`, force-push, worktree ligado, bare, symlinks, junções) ficam nos demais arquivos de `backend/tests/connectors/` (`test_selection.py`, `test_folder_connector.py`, `test_git_*.py`), sempre sobre árvores e repositórios sintéticos.

**Conector novo:** subpacote em `connectors/` com `AGENTS.md`, implementa `Connector`, entra em `SettingsConnectorFactory` e ganha uma implementação de `ContractSource` registrada em `CONTRACT_SOURCES`.

## Referências

- gitignore (formato dos padrões): <https://git-scm.com/docs/gitignore>
- `pathspec` (gitwildmatch em Python): <https://github.com/cpburnz/python-pathspec>
- `safe.directory`: <https://git-scm.com/docs/git-config#Documentation/git-config.txt-safedirectory>
- Clone parcial (`--filter=blob:none`): <https://git-scm.com/docs/partial-clone>
- `protocol.allow`: <https://git-scm.com/docs/git-config#Documentation/git-config.txt-protocolallow>
