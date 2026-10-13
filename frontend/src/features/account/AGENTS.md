# frontend/src/features/account/

**Função**: autosserviço da conta logada. Telas `/account/profile` (e-mail somente leitura com status de verificação e reenvio do link; nome, idioma e tema) e `/account/security` (troca de senha; sessões abertas, encerrar uma ou todas as outras).

**Entra aqui**:

- `ProfilePage.tsx` (`EmailSection` + `ProfileForm`) e `SecurityPage.tsx` (`ChangePasswordForm` + `SessionsSection`, que lista cada sessão com `SessionItem`, + `LogoutAllSection`, "Sair de todas as sessões" com confirmação: `POST /v1/auth/logout-all` encerra todas, inclusive esta, e os guardas levam ao login; 401 também conta como saída).
- Peças (confirmações com `components/ConfirmDialog.tsx`): `AccountPage` (coluna com o `h1`), `AccountSection` (bloco com borda rotulado pelo `h2`, consultável como `region`), `device.ts` (`deviceLabel`: "Chrome no Windows" a partir de `lib/userAgent.ts`).

**Não entra aqui**: chamadas de API (`lib/api/account.ts` e `useUpdateProfile` de `lib/api/auth.ts`), formatação de datas (`lib/intl.ts`), campos e alertas de formulário compartilhados (`components/TextField.tsx`, `components/FormAlert.tsx`), regras de senha e nome (`lib/schemas.ts`), telas públicas (`features/auth/`), textos (`i18n/locales/`, chaves `account.*`).

**Convenções locais**:

- Perfil: salva nome, idioma e tema num só `PATCH /v1/me` (otimista: o tema muda na hora pelo `useTheme` do shell). O idioma lista os idiomas do i18n mais o salvo no perfil; trocar o idioma ainda não muda a interface (só existe pt-BR).
- Senha: `invalid_current_password` aparece no campo "Senha atual" (com foco); outros erros no `FormAlert`. O backend encerra as outras sessões e mantém esta.
- Sessões: encerrar a atual é logout (confirmação; a sessão sai do cache com `endSession` e o `RequireAuth` manda para `/login` limpo). "Encerrar todas as outras" revoga uma a uma (a API não tem chamada única que preserve a atual; `POST /v1/auth/logout-all` encerra também esta).
- Datas: relativas e absolutas com `Intl` no idioma da interface; o "agora" vem de `useClock()` (`hooks/use-clock.ts`), fixado nos testes.

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. Telas pela árvore real (`renderWithProviders({ path: "/account/..." })`, com o "agora" fixo em `TEST_NOW`) e MSW (`sessionStore()` para sessões que de fato somem, `resendVerificationTooMany(seconds)`, `changePasswordInvalidCurrent`…).

**Leia também**: [../AGENTS.md](../AGENTS.md); [../../lib/api/AGENTS.md](../../lib/api/AGENTS.md); `docs/specs/openapi.json` (`/v1/me`, `/v1/me/password`, `/v1/me/sessions`, `/v1/auth/email/resend`).
