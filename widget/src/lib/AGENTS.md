# widget/src/lib/

**Função**: funções puras e pequenas do widget: o subconjunto seguro de Markdown das respostas (`markdown.ts`), a validação dos atributos de aparência e a cor de contraste (`appearance.ts`) e o ponteiro da conversa no navegador (`storage.ts`).

**Entra aqui**: código sem Lit e sem rede, testado isoladamente.
**Não entra aqui**: templates (`../element/`), chamadas HTTP (`../api/`).

**Convenções locais**:

- O Markdown produz uma árvore, nunca HTML; só links `http`/`https` viram link, e `[n]` só vira citação quando `n` existe.
- O armazenamento guarda só `{conversation_id, visitor_token, identity_sub, saved_at}` na chave `knobridge:v1:<widget-key>`; todo acesso em `try/catch`, com memória como reserva (modo `none` ou armazenamento bloqueado).
- Avisos de atributo inválido só em desenvolvimento (`devWarn`).

**Como testar**: de `widget/`, `pnpm test`.

**Leia também**: [docs/specs/widget.md](../../../docs/specs/widget.md), seções "Atributos", "Comportamento" e "Histórico no navegador".
