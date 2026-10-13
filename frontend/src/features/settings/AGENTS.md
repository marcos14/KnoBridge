# frontend/src/features/settings/

**Função**: configurações do workspace em `/w/:workspaceId/settings` (owner ou admin). Seções "Geral" (nome do workspace e identificador (slug) somente leitura) e "Níveis de resposta" (plano 0009, [produtos-e-niveis.md](../../../../docs/specs/produtos-e-niveis.md)).

**Entra aqui**:

- `WorkspaceSettingsPage.tsx`: `h1` e a seção "Geral", com o formulário do nome, e a seção de níveis.
- `LevelsSection.tsx`: os três níveis (Usuário final, Suporte, Desenvolvimento e produto), um formulário por nível (`role="form"` com o nome do nível): credencial (`Select`, com "Nenhuma (nível desligado)"), modelo (texto livre com as sugestões de `chatModelSuggestions` pelo tipo da credencial, num `datalist`), temperatura, instruções (o texto efetivo; com texto diferente do padrão, "Restaurar padrão" põe o padrão de volta) e o custo estimado por resposta (`formatUsd`, ou "sem preço"). Nível sem credencial e modelo mostra o aviso de que o chat nele não funciona; sem credencial cadastrada, link para `/providers`.
- `levelForm.ts` (puro, com teste): schema (credencial e modelo juntos ou nenhum, modelo sem espaços, temperatura de 0 a 2 com vírgula ou ponto, instruções até 20 000), valores iniciais e o corpo do `PATCH`.

**Não entra aqui**: membros e convites (`features/members/`), produtos (`features/products/`), perfil e segurança da conta (`features/account/`), chamadas de API (`lib/api/workspaces.ts`, `lib/api/levels.ts`), schema do nome (`workspaceNameField` em `lib/schemas.ts`), textos (`i18n/locales/`, chaves `workspaceSettings.*`).

**Convenções locais**:

- O nome salvo vai para o cache do `me` (`useRenameWorkspace`), e o seletor de workspace o mostra na hora, sem nova busca.
- Os formulários são montados com `key` do workspace: trocar de workspace recomeça com os dados do outro.
- Nível: o `PATCH` manda todos os campos; instruções iguais ao texto padrão (sem contar espaços nas pontas) vão como `null`, para o workspace seguir o padrão das próximas versões. Depois de salvar, o formulário recomeça com o que a API devolveu e o checklist do Início é recarregado.
- Formulários com react-hook-form + zod, `noValidate`, erros da API pelo `code` no `FormAlert`.

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. Pela árvore real (`renderWithProviders({ path: "/w/<id>/settings" })`) com MSW: `renameWorkspaceOk` padrão, `renameWorkspaceFails(status, code)`; níveis com `levelStore(initial)` (o `PATCH` aplica os campos como o backend; `changes`), `workspaceLevelsAs`, `workspaceLevelsServerError`, `updateLevelFails` e as fábricas de `test/levelFactories.ts`.

**Leia também**: [../AGENTS.md](../AGENTS.md); [../../lib/api/AGENTS.md](../../lib/api/AGENTS.md); `docs/specs/openapi.json` (`PATCH /v1/workspaces/{workspace_id}`, `GET .../levels`, `PATCH .../levels/{level}`).
