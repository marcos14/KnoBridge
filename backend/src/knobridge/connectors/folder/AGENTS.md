# backend/src/knobridge/connectors/folder/

**Função**: conector de pasta local (decisão D4 do [plano 0003](../../../../../docs/planos/0003-primeiro-conhecimento.md)): cada arquivo selecionado da pasta vira um documento `file`, com detecção incremental por hash de conteúdo.

**Entra aqui**: `connector.py` com `FolderConnector(config, allowed_root=, max_file_bytes=, max_document_bytes=, include_globs=, exclude_globs=, trust_mtime=True)`, `create_folder_connector(config, settings, include_globs=, exclude_globs=)` (raiz e limites vindos de `Settings`) e `FolderCursor`.
**Não entra aqui**: regras de seleção (`../selection.py`, compartilhadas com o Git), validação da configuração (`ingestion/source_config.py`), banco.

**Convenções locais**:
- Cursor: `{"kind": "folder", "version": 1, "entries": {caminho: [hash, tamanho, mtime_ns]}}`. O hash guardado são os 32 primeiros caracteres hex (128 bits) do SHA-256 do conteúdo: colisão desprezível para detectar mudança, e o cursor de uma pasta com 10 mil arquivos fica em torno de 1 MB de JSONB. O hash completo do documento vem de `RawDocument.content_hash` no `fetch`.
- Atalho `trust_mtime`: com tamanho e mtime iguais ao do cursor, o hash anterior é reaproveitado sem ler o arquivo. Mudar só o mtime (ex.: `touch`) atualiza o cursor sem gerar mudança. `trust_mtime=False` relê tudo.
- A raiz é resolvida a cada chamada (a pasta pode sumir ou ser religada entre execuções); `test_connection` falha com `PathOutsideRootError` ou `SourceUnavailableError`.
- `fetch` revalida a chave pela seleção (o que a listagem não listaria é `DocumentNotFoundError`) e só aceita `DocumentKind.FILE`. `metadata` traz `path`, `size_bytes` e `format`: `document` (PDF/Office, bytes para o parser) ou `text`.

**Como testar**: de `backend/`, `uv run pytest tests/connectors` (`test_folder_connector.py` e a suíte de contrato).

**Leia também**: [connectors/AGENTS.md](../AGENTS.md); [tests/connectors/AGENTS.md](../../../../tests/connectors/AGENTS.md).
