# widget/src/chat/

**Função**: a conversa do visitante sem renderização (`controller.ts`): reabre o histórico pelo ponteiro guardado no navegador, cria a conversa na primeira pergunta, consome o stream da resposta, transforma falhas em mensagens (429 com os minutos de espera, rede, `widget_unavailable`) e reenvia em "Tentar de novo".

**Entra aqui**: estado das mensagens (`ViewMessage`), regras da conversa e os eventos `knobridge-*` ligados a ela (`message-sent`, `answer`, `error`), emitidos pelo `ChatHost` que o elemento fornece.
**Não entra aqui**: HTTP (`../api/`), templates e foco (`../element/`), o formato do armazenamento (`../lib/storage.ts`).

**Convenções locais**:

- Relógio e `sub` da identidade injetados no construtor (determinismo nos testes; a identidade assinada chega na F4.2 do plano 0010).
- 401 ou `not_found` esquecem o ponteiro; a próxima pergunta abre conversa nova.
- O `detail` dos eventos nunca leva texto da pergunta, da resposta nem a identidade.

**Como testar**: de `widget/`, `pnpm test`.

**Leia também**: [docs/specs/widget.md](../../../docs/specs/widget.md), seções "Comportamento" e "Histórico no navegador".
