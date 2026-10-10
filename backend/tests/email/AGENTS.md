# backend/tests/email/

**Função**: testes de `src/knobridge/email/`: renderização dos templates, montagem de links, adaptador SMTP e o contrato do fake de envio.

**Entra aqui**: `test_rendering.py` (templates, assuntos, links, escape de HTML, `describe_duration`), `test_sender.py` (`SmtpEmailSender` contra servidor local e `FakeEmailSender`), `test_delivery.py` (`deliver_quietly`: envio, falha engolida e log sem dados pessoais, com `structlog.testing.capture_logs`) e `email_support.py` com o servidor SMTP em processo (`smtp_server`, `aiosmtpd` em `127.0.0.1`, porta escolhida pelo sistema, com login opcional e recusa de destinatário configurável), importado pelo nome.
**Não entra aqui**: o fake em si (`tests/fakes/email_sender.py`), testes de fluxos que disparam e-mail (ficam nos testes de `tenancy/` e `api/`, usando o fake).

**Convenções locais**:
- Nada de servidor SMTP externo nem rede: o servidor de teste roda no loop do próprio teste (`asyncio.run`), sem thread e sem `sleep`.
- Datas dos cabeçalhos via `FrozenClock`.
- Tokens, endereços e nomes sintéticos (`@example.com`).

**Como testar**: de `backend/`, `uv run pytest tests/email` (sem Docker).

**Leia também**: [email/AGENTS.md](../../src/knobridge/email/AGENTS.md); [tests/AGENTS.md](../AGENTS.md).
