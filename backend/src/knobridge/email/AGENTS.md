# backend/src/knobridge/email/

**Função**: e-mail transacional em pt-BR (redefinição de senha, verificação de e-mail, convite para workspace e definição de senha inicial): a interface de envio, o adaptador SMTP e a renderização dos templates.

**Entra aqui**:
- `sender.py`: `OutgoingEmail` (destinatário, assunto, texto e HTML), `EmailSender` (Protocol com `send`), `SmtpEmailSender` (`aiosmtplib`, uma conexão por mensagem, `from_settings`, cabeçalho `Date` pelo `Clock`) e `EmailDeliveryError` (502, código `email_delivery_failed`).
- `rendering.py`: `EmailTemplate`, `SUBJECTS`, `LINK_PATHS` (rotas do painel que consomem cada token), `describe_duration` (validade em pt-BR) e `EmailComposer` (`password_reset`, `email_verification`, `invitation`, `initial_password`, `link`, `render`, `from_settings`).
- `templates/`: os templates Jinja2, um `.txt` e um `.html` por e-mail.

**Não entra aqui**: emissão e consumo dos tokens (`security/tokens.py`), regras de quando enviar cada e-mail (serviços de `tenancy/` e rotas de `api/`), o fake de testes (`tests/fakes/email_sender.py`), leitura de variável de ambiente (`core/settings.py`).

**Convenções locais**:
- Quem envia depende só de `EmailSender`; produção injeta `SmtpEmailSender.from_settings(settings)` e os testes, `FakeEmailSender`. Nenhum teste fala com servidor SMTP externo (o teste do adaptador usa um servidor `aiosmtpd` em processo, em `127.0.0.1`).
- Link sempre por `EmailComposer.link`: `public_base_url` + rota de `LINK_PATHS` + `?token=` codificado. Rota nova do painel que consome token: atualize `LINK_PATHS` junto com o frontend.
- Nunca logar destinatário, token nem corpo do e-mail; em falha, só o tipo do erro.
- E-mail novo: valor em `EmailTemplate`, assunto em `SUBJECTS`, rota em `LINK_PATHS`, os dois templates e o caso no teste parametrizado de `tests/email/test_rendering.py`.

**Como testar**: de `backend/`, `uv run pytest tests/email` (sem Docker). Gate da suíte inteira: `uv run pytest`.

**Leia também**: [templates/AGENTS.md](templates/AGENTS.md); [tests/email/AGENTS.md](../../../tests/email/AGENTS.md); [tests/fakes/AGENTS.md](../../../tests/fakes/AGENTS.md); [security/AGENTS.md](../security/AGENTS.md); guia [subir-ambiente.md](../../../../docs/guias/subir-ambiente.md) (Mailpit em dev).
