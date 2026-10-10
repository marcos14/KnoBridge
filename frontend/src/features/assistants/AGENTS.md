# frontend/src/features/assistants/

**Função**: configuração dos assistentes do workspace em `/w/:workspaceId/assistants` (owner, admin e editor; viewer recebe 403 na rota e não vê o item de menu). Lista com status, criação, edição e exclusão.

**Entra aqui**:

- `AssistantsPage.tsx`: `h1`, "Novo assistente" (só quando há provedor; sem nenhum, um aviso com link para `/providers`), tabela paginada no navegador (20 por página) com nome e descrição, provedor e modelo, status ("Ativo"/"Inativo") e as ações "Editar" e "Excluir" (com `ConfirmDialog`, que avisa que as conversas do assistente também são excluídas e sugere desativar).
- `AssistantDialog.tsx`: diálogo de criar/editar com react-hook-form + zod: nome, descrição, prompt de sistema, provedor (lista de `useProviders`), modelo, temperatura, idioma, tom, mensagem de "sem fonte" e ativo.
- `assistantForm.ts`: schema com os limites do contrato, `parseTemperature` (aceita vírgula ou ponto, 0 a 2), valores iniciais e o corpo enviado (funções puras, com teste).

**Não entra aqui**: chamadas de API (`lib/api/assistants.ts`, `lib/api/providers.ts`), credenciais (`features/providers/`), chat de teste e conversas (próximas áreas), textos (`i18n/locales/`, chaves `assistants.*`).

**Convenções locais**:

- Criação e edição enviam todos os campos. Mensagem de "sem fonte" em branco faz o backend gravar a mensagem padrão (que volta preenchida na próxima edição).
- Excluir apaga as conversas do assistente (`ON DELETE CASCADE`); desativar preserva o histórico e bloqueia conversa nova.
- Erros da API (`assistant_name_taken`, `assistant_provider_invalid`, …) aparecem no `FormAlert` pelo `code`.

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. Pela árvore real (`renderWithProviders({ path: "/w/<id>/assistants" })`) com MSW: `assistantStore(initial)` (mudanças persistem; `created`, `changes`, `deleted`; mensagem vazia vira `DEFAULT_NO_SOURCE_MESSAGE`), `assistantsAs`, `providersAs`, `assistantsServerError`, `createAssistantFails`, `updateAssistantFails`, `deleteAssistantFails`.

**Leia também**: [../AGENTS.md](../AGENTS.md); [../providers/AGENTS.md](../providers/AGENTS.md); `docs/specs/openapi.json` (`/v1/workspaces/{workspace_id}/assistants`).
