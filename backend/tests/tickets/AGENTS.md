# backend/tests/tickets/

**Função**: testes de `src/knobridge/tickets/`: unitários da validação do chamado, dos itens do lote, do formato do token, da cifra do segredo do webhook, da anonimização, do Markdown, da leitura do arquivo de upload e da prévia, e, contra Postgres real, o conector interno `tickets`, a RLS das tabelas de chamados, a busca do token de envio pelo prefixo, chaves, `CHECK`s, FKs compostas e exclusões.

**Entra aqui**:
- `tickets_support.py`: `run_db`, `seed` (workspace novo com fonte `tickets`, token de envio, entrada `pending` na caixa, assistente, conversa e pedido `pending` sobre uma resposta "sem fonte"), `count_by_model`, `new_token`, `tickets_source`, `pending_entry`, `pending_request` e `add_answer`.
- `conftest.py`: `rls_database_url` (o banco como dono e como não dono).
- `test_tickets_rls.py`: RLS forçada nas três tabelas, isolamento entre workspaces (leitura, alteração, exclusão e inserção alheia recusada), token achado pelo `token_prefix` só em modo de sistema e prefixo único na instância.
- `test_tickets_constraints.py`: fonte `tickets`, execução `ingest` e documento `ticket` aceitos; um token por fonte e formatos; `(source_id, external_id)` único; os `CHECK`s de estado da caixa e do pedido; um pedido por mensagem; FKs compostas; cascatas da fonte, da conversa, do assistente e do workspace; colunas e `CHECK`s do webhook em `assistants`.
- `test_webhook_secret.py` (unitário): cifra e decifra do segredo, presa ao assistente e com chave própria.
- `test_webhook_signature.py` (unitário): HMAC do `t.corpo`, cabeçalho e a verificação do destino (tolerância nas bordas, corpo ou segredo trocados, pares extras, vários `v1`, cabeçalho malformado).
- `test_webhook_send.py` (unitário): formato do `kbw_`, `check_webhook_url` com os motivos, cabeçalhos, corpo compacto, destino verificado de novo antes de enviar e uma tentativa assinada para um receptor HTTP local (`127.0.0.1` na lista de permissão) que confere a assinatura. O serviço com banco fica em `tests/api/test_ticket_webhook.py`.
- `test_ticket_receipt.py` (unitário): a resposta 2xx lida em `ticket_id` e `url` (número como texto, campos inválidos ignorados, corpo vazio ou não JSON) e `start_delivery` com o Temporal fora (só loga). A entrega com banco fica em `tests/workers/test_ticket_delivery.py`.
- `test_ticket_summary.py` (unitário): o resumo do pedido (conversa como dado, parâmetros, corte em 600, resposta vazia, falha do provedor e provedor que não abre → `None`).
- `test_ticket_wire.py` (unitário): os exemplos válido e inválido da spec (lidos de `tests/fixtures/tickets/`), payload canônico com padrões e UTC, hash que ignora fuso e ordem de chaves, as regras extras e o teto de 50 problemas.
- `test_ticket_items.py` (unitário): `check_items` (item inválido sem derrubar o lote, `external_id` nulo quando inválido, `ticket_too_large`, `duplicate_in_batch`, problemas da forma do item, remoções) e `count`.
- `test_ingest_token_format.py` (unitário): formato do `kbi_`, prefixo e conferência em tempo constante.
- `ticket_payload_support.py`: `SPEC_EXAMPLE` (o exemplo válido da spec, literal), `SPEC_MARKDOWN` (o layout da spec para ele), `minimal`, `message` e `ticket` (valida um payload com campos trocados).
- `test_ticket_model.py` (unitário): o `TicketIn` como o Markdown o usa: padrões, número e data da citação e tipos de `custom_fields` (os problemas de validação ficam em `test_ticket_wire.py`).
- `test_anonymize.py` (unitário): cada regra com positivos e negativos (e-mail em URL, versão x IP, CPF/CNPJ que não validam, Luhn, telefone com e sem DDI/DDD, limites de dígito), nomes declarados em várias grafias, precedência e numeração, marcador nunca olhado de novo.
- `test_upload_files.py` (unitário): formato pela extensão, JSONL linha a linha (BOM, linhas em branco, linha inválida), JSON em lista e `{"items"}` decodificado em blocos mínimos (número e caractere cortados no fim do bloco), leitura em fluxo sem chegar ao fim do arquivo no primeiro elemento, arquivo vazio e cada forma de JSON malformado.
- `test_upload.py` (unitário): elemento → item (chamado puro, `op` desconhecido, não objeto, linha inválida), `check_indexed_items` com duplicados entre blocos, blocos na ordem do arquivo, relatório por linha ou posição e truncado, e a prévia (marcadores aplicados, sem anonimização, marcador já escrito no chamado, chamado inválido, não objeto e acima de 1 MiB). A gravação fica em `tests/api/test_ticket_upload.py`.
- `test_ticket_markdown.py` (unitário): Markdown igual ao da spec, metadados, notas internas fora por padrão e dentro quando ligadas, sem anonimização, marcador estável entre campos, seções omitidas, conversão dos corpos, hash estável e os chunks do chamado renderizado.
- `tickets_connector_support.py`: `World` (fonte `tickets` com config por teste e token de envio, opcional; `connector()` pela fábrica de produção com relógio fixo), `world`, `ticket`, `upsert`, `delete`, `push` (itens pelas regras reais da caixa: `check_items` + `apply_items`), `entry` e `settle` (um fechamento numa transação no escopo do workspace, como a do motor).
- `test_tickets_connector.py`: o conector `tickets` sobre Postgres real: listagem (adicionado, alterado, lápide e status fora de `statuses` como remoção), `fetch` com Markdown anonimizado e metadados, notas internas e anonimização conforme a fonte, recusas de `fetch` (não pendente, lápide, versão nova filtrada, ausente, payload inválido `ticket_invalid`), fechamento indexado que apaga o bruto e é idempotente, versão chegada depois do `fetch` preservada, remoções (`deleted`, `filtered`, entrada de novo em `statuses` intocada), erro truncado com o payload mantido, teste de conexão pelo token, ACL aberta, cursor alheio, fábrica com fonte de outro tipo e isolamento entre workspaces. O contrato compartilhado fica em `tests/connectors/contract/`; o workflow, em `tests/workers/test_tickets_ingestion.py`.

**Não entra aqui**: rotas (`tests/api/`), cadeia de migrações (`tests/migrations/`), a config da fonte (`tests/ingestion/test_source_config.py`).

**Convenções locais**:
- Os de banco levam `@pytest.mark.integration`; o banco é compartilhado, então cada teste cria seus workspaces com valores únicos.
- Tokens e segredos sintéticos (`kbi_<prefixo>_<segredo>` gerado no teste, `kbw_` de letras repetidas), nunca reais; chamados inventados e mínimos.

**Como testar**: de `backend/`, `uv run pytest tests/tickets` (exige Docker); só os unitários: `uv run pytest tests/tickets -m "not integration"`.

**Leia também**: [tickets/AGENTS.md](../../src/knobridge/tickets/AGENTS.md); [tests/AGENTS.md](../AGENTS.md).
