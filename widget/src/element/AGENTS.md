# widget/src/element/

**Função**: o elemento `<knobridge-chat>` em Lit (`knobridge-chat.ts`): atributos (inclusive `identity`), métodos públicos (`open`, `close`, `toggle`, `newConversation`, `setIdentity`), modos balão e embutido, foco e teclado. Ao lado, os templates das mensagens e citações (`templates.ts`), da avaliação e do formulário de chamado sob cada resposta (`actions.ts`), o campo de pergunta (`composer.ts`), a aparência efetiva (`view.ts`: atributo válido vence o painel) e os estilos (`styles.ts`: variáveis `--knobridge-*` vencem os dois).

**Entra aqui**: renderização, acessibilidade (ARIA, `role="log"` com `aria-live`, `aria-busy` durante o stream, foco ao abrir e ao fechar com `Esc`), eventos de interface (`knobridge-ready`, `-open`, `-close`).
**Não entra aqui**: regras da conversa e chamadas à API (`../chat/`, `../api/`), textos (`../i18n/`).

**Convenções locais**:

- A propriedade do atributo `open` é `isOpen` (o nome `open` é do método) e a do atributo `title` é `chatTitle` (`title` é a dica nativa do `HTMLElement`).
- Sob cada resposta terminada (`completed` ou `no_source`), `templates.ts` chama `answerActions(message)` do contexto, que o elemento liga a `renderAnswerActions` de `actions.ts` com o que a configuração permite (`feedback_enabled`, `ticket_enabled` e o `ticket_requests_enabled` da conversa). O formulário de chamado tem `part="ticket-form"`, erros ligados por `aria-describedby` e foco no primeiro campo com erro.
- O campo de pergunta é `#input` e o formulário dele `form[part=composer]` (há outros formulários dentro das mensagens).
- Todo texto da API passa por template do Lit (escapado); variáveis CSS por `styleMap`, nunca atributo `style`.
- Testes consultam por papel, ARIA e texto; cada arquivo de teste até ~400 linhas.

**Como testar**: de `widget/`, `pnpm test` (jsdom; helpers em `../test/dom.ts`).

**Leia também**: [docs/specs/widget.md](../../../docs/specs/widget.md), seções "Atributos", "Métodos", "Eventos", "Aparência", "Comportamento" e "Acessibilidade".
