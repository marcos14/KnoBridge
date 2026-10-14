# widget/src/element/

**Função**: o elemento `<knobridge-chat>` em Lit (`knobridge-chat.ts`): atributos, métodos públicos (`open`, `close`, `toggle`, `newConversation`), modos balão e embutido, foco e teclado. Ao lado, os templates das mensagens e citações (`templates.ts`), o campo de pergunta (`composer.ts`), a aparência efetiva (`view.ts`: atributo válido vence o painel) e os estilos (`styles.ts`: variáveis `--knobridge-*` vencem os dois).

**Entra aqui**: renderização, acessibilidade (ARIA, `role="log"` com `aria-live`, `aria-busy` durante o stream, foco ao abrir e ao fechar com `Esc`), eventos de interface (`knobridge-ready`, `-open`, `-close`).
**Não entra aqui**: regras da conversa e chamadas à API (`../chat/`, `../api/`), textos (`../i18n/`).

**Convenções locais**:

- A propriedade do atributo `open` é `isOpen` (o nome `open` é do método) e a do atributo `title` é `chatTitle` (`title` é a dica nativa do `HTMLElement`).
- `renderAnswerActions(message)` é o ponto de extensão sob cada resposta terminada; feedback e "Abrir chamado" entram por ele na F4.2 do plano 0010.
- Todo texto da API passa por template do Lit (escapado); variáveis CSS por `styleMap`, nunca atributo `style`.
- Testes consultam por papel, ARIA e texto; cada arquivo de teste até ~400 linhas.

**Como testar**: de `widget/`, `pnpm test` (jsdom; helpers em `../test/dom.ts`).

**Leia também**: [docs/specs/widget.md](../../../docs/specs/widget.md), seções "Atributos", "Métodos", "Eventos", "Aparência", "Comportamento" e "Acessibilidade".
