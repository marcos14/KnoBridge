# backend/tests/connectors/contract/

**Função**: a suíte de contrato que todo `Connector` precisa passar (seção 5 do [AGENTS.md da raiz](../../../../AGENTS.md)), escrita uma vez e rodada contra cada conector.

**Entra aqui**:
- `contract_support.py`: o `Protocol` `ContractSource` (`connector()`, `add`, `change`, `remove`, `break_source`), uma implementação por conector (`FakeContractSource` sobre `fakes.connector.FakeConnector`, `FolderContractSource` sobre uma pasta em `tmp_path` com mtimes fixos) e o registro `CONTRACT_SOURCES` (nome → fábrica que recebe `tmp_path`).
- `test_connector_contract.py`: os testes `test_contract_*`, parametrizados pela fixture `source` sobre `CONTRACT_SOURCES`: primeira listagem adiciona tudo; listar com o próprio cursor não muda nada; adicionado, alterado e removido; cursor sobrevive a ida e volta em JSON; `fetch` devolve o conteúdo e o SHA-256; ref desconhecida ou removida dá `DocumentNotFoundError`; ACL aberta; `test_connection` passa na fonte legível e falha com `ConnectorError` na quebrada; cursor alheio dá `InvalidCursorError`.

**Não entra aqui**: testes específicos de um conector (ficam em `tests/connectors/test_<conector>_connector.py`).

**Convenções locais**: conector novo entra implementando `ContractSource` aqui e registrando a fábrica em `CONTRACT_SOURCES` (ex.: o Git faz commit em `add`/`change`/`remove`). Os documentos do contrato são texto pequeno, com chaves em subpastas, para valerem em qualquer conector de árvore.

**Como testar**: de `backend/`, `uv run pytest tests/connectors/contract`.

**Leia também**: [tests/connectors/AGENTS.md](../AGENTS.md); [connectors/AGENTS.md](../../../src/knobridge/connectors/AGENTS.md).
