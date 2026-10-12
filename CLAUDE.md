# CLAUDE.md

Este repositório usa `AGENTS.md` como fonte única de instruções para agentes de IA e humanos. Este arquivo existe só para que o Claude Code carregue aquelas instruções automaticamente.

@AGENTS.md

Regras adicionais, válidas só para o Claude Code:

- Antes de editar qualquer arquivo em uma pasta, leia o `AGENTS.md` dela. O Claude Code não carrega `AGENTS.md` de subpastas sozinho.
- Não crie `CLAUDE.md` em subpastas. A instrução por pasta é o `AGENTS.md`.
- Regras que só fazem sentido para o Claude Code (hooks, permissões, skills) entram aqui. Todo o resto vai para `AGENTS.md`.
- Na etapa 3.1 do `AGENTS.md` (entender o pedido), use a ferramenta AskUserQuestion ou perguntas diretas; não avance para o plano enquanto houver dúvida.
- Na etapa 3.3 (executar subfase), rode cada subfase com a ferramenta Agent com `isolation: "worktree"` (ou `claude -p` numa sessão nova), passando no prompt só o trecho do plano da subfase, os `AGENTS.md` envolvidos e os arquivos listados no contexto necessário. A sessão principal é o orquestrador: valida, commita e atualiza o frontmatter.
