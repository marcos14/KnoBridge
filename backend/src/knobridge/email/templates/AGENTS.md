# backend/src/knobridge/email/templates/

**Função**: templates Jinja2 dos e-mails transacionais, em pt-BR, carregados por `EmailComposer` (`rendering.py`) com `PackageLoader`.

**Entra aqui**:
- `_layout.html` e `_layout.txt`: estrutura comum (saudação, link, validade, aviso de "ignore", rodapé).
- Um par `<nome>.html` + `<nome>.txt` por valor de `EmailTemplate` (`password_reset`, `email_verification`, `invitation`, `initial_password`), estendendo o layout correspondente.

**Não entra aqui**: assunto (fica em `SUBJECTS`, em `rendering.py`), lógica de montagem de link, código Python.

**Convenções locais**:
- `.html` tem autoescape ligado; `.txt` não tem e não pode conter tags. `StrictUndefined`: variável ausente é erro.
- Variáveis disponíveis em todos: `link`, `expires_in` (texto já em pt-BR), `base_url`. O convite recebe também `workspace_name` e `inviter_name`.
- HTML de e-mail: tabelas e estilos inline, sem CSS externo, sem imagens remotas, sem JavaScript.
- Blocos do layout: `title` (só HTML), `content`, `action` (texto do botão, só HTML) e `ignore_note`.

**Como testar**: de `backend/`, `uv run pytest tests/email/test_rendering.py`.

**Leia também**: [email/AGENTS.md](../AGENTS.md).
