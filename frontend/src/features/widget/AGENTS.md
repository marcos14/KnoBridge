# frontend/src/features/widget/

**Função**: tela **Widgets** do painel, em `/w/:workspaceId/widgets`, `/widgets/new` e `/widgets/:widgetId`, só para owner e admin. Editor e viewer não veem o item de menu e recebem 403 na rota (`minRole: "admin"` em `app/shell/navItems.ts`; a API também responde 403). Ali se cria e configura o chat embutível de um produto, com prévia ao vivo, o trecho de instalação e a identidade assinada. Contrato em `docs/specs/widget.md`.

**Entra aqui**:

- `WidgetsPage.tsx`: elemento das três rotas. Lê o `:widgetId` com `useMatch`; `new` cria.
- `WidgetsList.tsx`: título, "Novo widget", `ListToolbar` sem ordenação (a API ordena por nome) com busca e os filtros de produto e estado na URL (`?q=&product=&active=`), e tabela paginada pela API. A tabela mostra nome e chave `kbp_`, produto, domínios (dois e "+N"), modo e estado. As ações são Configurar, Ativar/Desativar e Excluir, esta com `ConfirmDialog` avisando que as conversas são apagadas. Há dois estados vazios com o próximo passo: criar o primeiro widget ou, sem produto, ir para Produtos.
- `WidgetDetail.tsx`: "Voltar para os widgets" e, conforme a rota:
  - criação: `WidgetEditor`;
  - widget existente: título com o estado, "Widget X criado" (vem do `state` da navegação depois do `POST`), `InstallPanel`, `WidgetEditor` e `SigningSecretPanel`; 404 vira "Widget não encontrado".
- `WidgetEditor.tsx`: formulário (react-hook-form + zod), com os campos em `WidgetFormFields.tsx`:
  - produto, só na criação: ele não muda;
  - nome e "Ativo";
  - origens, uma por linha;
  - aparência: modo, posição (desligada no modo embutido), tema, cor com o aviso de contraste abaixo de 3:1, título, saudação e texto do campo;
  - recursos: 👍/👎 e "Abrir chamado", com o aviso quando o produto não tem webhook;
  - limites.
    O 422 `widget_origin_invalid` aparece no campo, origem por origem. Na edição, ao lado do formulário fica a `WidgetPreview` com os valores ainda não salvos.
- `WidgetPreview.tsx` + `previewElement.ts`:
  - injeta uma única vez o `<script id="knobridge-widget-script">` de `<origem>/widget/v1/knobridge-chat.js`;
  - monta à mão um `<knobridge-chat>` com `widget-key`, `mode="inline"`, `storage="none"` e `api-base`, mais os atributos de aparência, trocados no lugar;
  - chave nova recria o elemento;
  - avisa que a prévia conversa de verdade.
- `InstallPanel.tsx`: chave pública e o trecho `<script>` + elemento do modo salvo (`installSnippets.ts`), com copiar.
- `SigningSecretPanel.tsx`: segredo `kbs_`. Ações:
  - gerar;
  - substituir, com confirmação;
  - remover, com confirmação.
    O segredo aparece uma vez e só existe no estado do componente. Abaixo ficam os exemplos de identidade (elemento, Python e Node, lendo `KNOBRIDGE_WIDGET_SIGNING_SECRET`).
- `widgetForm.ts` (schema, padrões da API, corpo do `POST` e diferença do `PATCH`), `installSnippets.ts`, `widgetPaths.ts`.

**Não entra aqui**:

- chamadas de API: `lib/api/widgets.ts`;
- validação das origens: `lib/widgetOrigins.ts`;
- contraste: `lib/colorContrast.ts`;
- o Web Component: pacote `widget/` da raiz;
- textos: `i18n/locales/`, chaves `widgets.*` e `apiErrors.widget_*`.

**Convenções locais**:

- A prévia usa a origem do painel (`window.location.origin`), que é a da instância e está sempre permitida. O script nunca é injetado duas vezes.
- O segredo de assinatura nunca vai para consulta, URL nem armazenamento: só para o estado do painel, até sair da tela.
- O `PATCH` leva só o que mudou. Sem mudança, nada é enviado ("Nada mudou.").

**Como testar**: de `frontend/`, rode `pnpm vitest run src/features/widget`. Os testes usam a árvore real (`renderWithProviders({ path: "/w/<id>/widgets..." })`) com MSW:

- `widgetStore(initial, productIds)` grava `created`, `changes`, `deleted`, `rotations`, `removals` e `listQueries`;
- `widgetsAs`, `widgetsServerError`, `widgetServerError` e `widgetActionFails(action, status, code, details)` simulam a API;
- os dados ficam em `@/test/widgetFactories`.

A prévia é testada com um `knobridge-chat` falso, registrado por `customElements.define` no próprio teste (o jsdom não carrega o script). O teste remove o `<script>` no `afterEach`. Clipboard pelo stub do `userEvent.setup()`.

**Leia também**: [../AGENTS.md](../AGENTS.md); [../../lib/api/AGENTS.md](../../lib/api/AGENTS.md); `docs/specs/widget.md`; `widget/AGENTS.md` (atributos do elemento); [ADR 0009](../../../../docs/adr/0009-canais-mcp-e-widget.md).
