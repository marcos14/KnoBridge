# widget/src/chat/

**Função**: a conversa do visitante sem renderização (`controller.ts`): reabre o histórico pelo ponteiro guardado no navegador, cria a conversa na primeira pergunta (com a identidade assinada, repassada como veio), troca de conversa quando o `sub` da identidade muda, consome o stream da resposta (um `done` com `no_source` apaga as citações já recebidas, resposta do modelo sem marcador `[n]`; um evento `step` marca a resposta como `searching`, e o elemento troca "Digitando…" por "Buscando mais informações…" até o primeiro texto, sem a consulta nem a contagem), transforma falhas em mensagens (429 com os minutos de espera, rede, `widget_unavailable`) e reenvia em "Tentar de novo". Em `actions.ts`, o que se faz com uma resposta terminada: 👍/👎 com comentário opcional no 👎 e "Abrir chamado" (resumo, e-mail quando a identidade não traz, nome opcional), com o pedido consultado a cada 10 s, no máximo 6 vezes.

**Entra aqui**: estado das mensagens (`ViewMessage`, com `feedback` e `ticketRequest`), estado dos formulários por resposta (`AnswerActions`, criado pelo `ChatController`), regras da conversa e os eventos `knobridge-*` ligados a ela (`message-sent`, `answer`, `feedback`, `ticket-requested`, `error`), emitidos pelo `ChatHost` que o elemento fornece.
**Não entra aqui**: HTTP (`../api/`), templates e foco (`../element/`), o formato do armazenamento (`../lib/storage.ts`).

**Convenções locais**:

- Relógio e identidade injetados no construtor (determinismo nos testes); o agendador da consulta do chamado é injetável em `AnswerActions` (os testes rodam as consultas à mão, sem esperar).
- A consulta do chamado para quando a conversa muda ("Nova conversa", outra identidade).
- 401 ou `not_found` esquecem o ponteiro; a próxima pergunta abre conversa nova.
- O `detail` dos eventos nunca leva texto da pergunta, da resposta nem a identidade.

**Como testar**: de `widget/`, `pnpm test`.

**Leia também**: [docs/specs/widget.md](../../../docs/specs/widget.md), seções "Comportamento" e "Histórico no navegador".
