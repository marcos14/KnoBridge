# frontend/src/i18n/locales/

**Função**: arquivos de tradução da interface, um JSON por idioma. `pt-BR.json` é a referência.

**Entra aqui**: `<idioma>.json` (ex.: `pt-BR.json`), com chaves em inglês agrupadas por área (`app.*`, `nav.*` (menu lateral: `nav.items.<área>`, `nav.adminItems.*`), `shell.*`, `workspaceSwitcher.*`, `userMenu.*`, `noWorkspace.*`, `workspaceSuspended.*`, `areas.*` (páginas esqueleto de Pipelines e Canais), `apiStatus.*`, `home.*`, `notFound.*`, `forbidden.*`, `authGuard.*`, `auth.*` (telas públicas: `auth.fields.*`, `auth.validation.*`, uma subchave por tela), `account.*` (perfil e segurança da conta: `account.profile.*`, `account.security.*`), `confirmDialog.*` e `dataTable.*` (componentes genéricos de `components/`), `members.*` (membros e convites; `members.roleNames.*` com o nome dos papéis com inicial maiúscula, para listas e seletores), `workspaceSettings.*`, `providers.*` (provedores de LLM: `providers.kinds.*`, `providers.form.*`), `assistants.*` (assistentes: `assistants.form.*`, com `assistants.form.tones.*`), `collections.*` (coleções: `collections.columns.*`, `collections.form.*`, `collections.detail.*`, `collections.search.*`), `sources.*` (fontes: `sources.columns.*`, `sources.kinds.*`, `sources.runStatus.*`, `sources.triggers.*`, `sources.cron.*` (leitura do cron, com plurais `_one`/`_other`, `sources.cron.days.0`–`6` e `sources.cron.presets.*`), `sources.form.*`, `sources.detail.*`, `sources.runs.*`, `sources.errors.*`, `sources.documents.*`), `chat.*` (chat dos membros: `chat.list.*`, `chat.assistants.*`, `chat.conversation.*`, `chat.message.*`, `chat.citations.*`, `chat.composer.*`, `chat.feedback.*`; também usadas pela resposta compartilhada de `components/`), `conversations.*` (tela de conversas: `conversations.stats.*`, `conversations.filters.*`, `conversations.columns.*`, `conversations.detail.*`), `audit.*` (telas de auditoria), `auditActions.*` (rótulo de cada ação de auditoria), `admin.*` (administração da instância: `admin.workspaces.*`, `admin.users.*`), `roles.*` (nome dos papéis em minúsculas, para usar no meio da frase), `apiErrors.*`, depois uma por feature).
**Não entra aqui**: código, textos que não aparecem na interface, mensagens de log (ficam em inglês no código).

**Convenções locais**:

- Chave nova entra primeiro no `pt-BR.json`; os tipos de `t()` derivam dele.
- Chaves em `camelCase`, aninhadas por área; nada de frase como chave. Exceções: em `apiErrors.*` a chave é o `code` da API como o backend o envia (`snake_case`), para o mapeamento ser direto; em `auditActions.*` é o código da ação com `.` trocado por `_` (ex.: `auth_login_failed`).
- Textos em pt-BR, sem HTML; interpolação com `{{variavel}}`.

**Como testar**: de `frontend/`, `pnpm test -- --coverage`; os testes dos componentes consultam pelos textos traduzidos.

**Leia também**: [../AGENTS.md](../AGENTS.md).
