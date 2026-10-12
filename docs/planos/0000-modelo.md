---
id: 0000
titulo: Modelo de plano (copie este arquivo; nunca execute)
slug: modelo
solicitado_por: usuario
criado_em: 2026-10-10
atualizado_em: 2026-10-10
status: rascunho            # rascunho | aguardando_aprovacao | aprovado | em_execucao | bloqueado | concluido | cancelado
aprovado_em: null
aprovado_por: null
concluido_em: null
branch: plano/0000-modelo
fases:
  - id: F1
    titulo: Nome da fase
    status: pendente        # pendente | em_execucao | concluida | bloqueada | cancelada
    subfases:
      - id: F1.1
        titulo: Nome da subfase
        status: pendente
        agente: null        # ex.: claude-code, codex, humano:<nome>
        iniciada_em: null
        concluida_em: null
        commit: null        # hash curto, preenchido na atualização seguinte do plano
      - id: F1.2
        titulo: Nome da subfase
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
decisoes: []
# Formato de cada item:
#  - id: D1
#    data: 2026-10-10
#    por: agente             # agente | usuario
#    decisao: o que foi decidido
#    motivo: por quê
#    alternativas: o que foi descartado
#    adr: null               # docs/adr/NNNN-... quando for decisão de arquitetura
pendencias_usuario: []
# Formato de cada item:
#  - id: P1
#    data: 2026-10-10
#    pergunta: o que depende do usuário
#    bloqueia: F1.2          # id da subfase bloqueada, ou null
#    status: aberta          # aberta | respondida
#    resposta: null
#    respondida_em: null
---

# Plano 0000 — <título>

## 1. Pedido original

Texto do pedido do usuário, nas palavras dele, citado.

## 2. Entendimento (perguntas e respostas)

| # | Pergunta | Resposta | Data |
|---|---|---|---|
| 1 | ... | ... | 2026-10-10 |

Resumo, após as respostas, do que será feito e do que fica fora do escopo.

## 3. Critérios de aceite

- [ ] ...

## 4. Fases e subfases

### F1 — <nome da fase>

Objetivo da fase em uma frase.

#### F1.1 — <nome da subfase>

- **Objetivo**: ...
- **Entregáveis**: arquivos e pastas que serão criados ou alterados.
- **Contexto necessário para o agente isolado**: lista exata de arquivos, specs, seções de `AGENTS.md` e deste plano que ele deve ler. Nada além disso.
- **Critérios de aceite**: comportamento esperado e os testes que devem existir (nomes ou cenários).
- **Depende de**: nenhuma / F1.0.
- **Tamanho**: pequeno / médio (ver seção 3.2 do `AGENTS.md` da raiz).

#### F1.2 — <nome da subfase>

- **Objetivo**: ...
- **Entregáveis**: ...
- **Contexto necessário para o agente isolado**: ...
- **Critérios de aceite**: ...
- **Depende de**: F1.1.
- **Tamanho**: ...

## 5. Decisões

Detalhe das entradas de `decisoes[]` quando uma linha no frontmatter não basta.

## 6. Pendências do usuário

Detalhe das entradas de `pendencias_usuario[]`.

## 7. Registro de andamento

- 2026-10-10 — plano criado; aguardando aprovação.

## 8. Encerramento

O que foi entregue, o que ficou fora e por quê, e o comando que demonstra o resultado.
