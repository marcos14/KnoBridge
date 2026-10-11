# frontend/src/app/shell/

**Função**: a moldura navegável das páginas autenticadas. Sidebar recolhível e responsiva, topbar, seletor de workspace, menu do usuário com tema, redirecionamento de `/`, estado de workspace suspenso e páginas esqueleto das áreas que ainda não têm feature.

**Entra aqui**:

- `AppShell.tsx`: `SidebarProvider` + link "pular para o conteúdo" + `AppSidebar` + `header` (alternar menu, `ApiStatus`, `UserMenu`) + `main` com o `<Outlet />`. 403 e 404 das rotas autenticadas aparecem dentro dele.
- `AppSidebar.tsx`: `nav` "Navegação principal" com os itens do workspace ativo filtrados pelo papel e o grupo "Administração da instância" (só superadmin). No celular vira um `Sheet` (diálogo) que fecha ao navegar.
- `navItems.ts`: `WORKSPACE_AREAS` (chave, caminho, papel mínimo, ícone) e `ADMIN_AREAS`; `workspaceNavItems`, `adminNavItems`, `areaMinRole`. **Fonte única**: o router guarda cada rota de área com o mesmo `minRole` do menu.
- `WorkspaceSwitcher.tsx` (lista de `me.workspaces`, troca a rota para `/w/:id`), `UserMenu.tsx` (perfil, segurança, tema claro/escuro/sistema, sair: vai para `/login` sem `?next=`, porque outra pessoa pode entrar em seguida no mesmo navegador; quem navega é o `RequireAuth`, que vê o marcador de logout explícito gravado pelo `useLogout`; uma navegação própria aqui correria com ele).
- `useTheme.ts`: aplica o tema do perfil no `<html>` (classe `dark`), espelha em `localStorage` para o primeiro paint e grava mudanças com `PATCH /v1/me` (otimista, via `useUpdateProfile`); em "sistema" acompanha a preferência do SO.
- `useActiveWorkspace.ts`: workspace da URL ou, fora de `/w/...`, o último usado.
- `HomeRedirect.tsx`: `/` → último workspace usado (`lib/lastWorkspace.ts`) ou o primeiro; sem nenhum, a tela "você ainda não participa de nenhum workspace" (superadmin vê atalho para `/admin/workspaces`).
- `WorkspaceLayout.tsx` + `useWorkspaceSuspended.ts`: guarda o último workspace e mostra "workspace suspenso" quando o `me` diz `suspended` ou quando qualquer query/mutação recebe 403 `workspace_suspended`.
- `AreaSkeletonPage.tsx`: título e estado vazio explicativo de Fontes, Pipelines e Canais.

**Não entra aqui**: telas de produto (vão para `features/<area>/` e substituem o esqueleto no `router.tsx`), guardas de rota (`features/auth/`), componentes shadcn (`components/ui/`), chamadas de API (`lib/api/`), textos (`i18n/locales/`).

**Convenções locais**:

- Item de menu novo: uma linha em `WORKSPACE_AREAS` (ou `ADMIN_AREAS`), a chave em `nav.items.*` do pt-BR e a rota em `router.tsx` com `workspaceArea(...)`.
- Menu e rotas são só conveniência: quem autoriza é o backend.
- Textos via `useTranslation()`, inclusive rótulos acessíveis (`aria-label`) e o título oculto do `Sheet`.

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. Testes pela árvore real (`renderWithProviders({ path })`) com MSW (`meAs(makeMe(...))`); tema e celular com `setPrefersDark`/`setMobileViewport` de `@/test/matchMedia`; menus do Radix abertos com `userEvent` e consultados por `menuitem`/`menuitemradio`.

**Leia também**: [../AGENTS.md](../AGENTS.md); [../../features/auth/AGENTS.md](../../features/auth/AGENTS.md); [../../components/ui/AGENTS.md](../../components/ui/AGENTS.md).
