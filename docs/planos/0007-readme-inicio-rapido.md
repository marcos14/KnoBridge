---
id: 0007
titulo: README com início rápido para quem quer experimentar o KnoBridge
slug: readme-inicio-rapido
solicitado_por: usuario
criado_em: 2026-10-12
atualizado_em: 2026-10-12
status: concluido
aprovado_em: 2026-10-12
aprovado_por: usuario
concluido_em: 2026-10-12
branch: plano/0005-chamados-por-api
fases:
  - id: F1
    titulo: README
    status: concluida
    subfases:
      - id: F1.1
        titulo: Reescrever o README da raiz com início rápido, próximos passos e seção curta de desenvolvimento
        status: concluida
        agente: claude-code-worktree
        iniciada_em: 2026-10-12
        concluida_em: 2026-10-12
        commit: null
decisoes:
  - id: D1
    data: 2026-10-12
    por: usuario
    decisao: "O README é para quem quer experimentar: passos numerados com chave de LLM real (sem o provedor fake no caminho principal); a seção de testes vira uma seção Desenvolver curta no fim"
    motivo: "o leitor do README quer ver o KnoBridge responder com citações no menor número de passos"
    alternativas: "foco em implantação; os dois públicos; caminho com o provedor fake; tirar os testes do README"
    adr: null
  - id: D2
    data: 2026-10-12
    por: agente
    decisao: "Caminho principal com OpenRouter (uma chave cobre embedding e chat; OpenAI direto como alternativa) e uma pasta de documentos do próprio usuário como primeira fonte (copiar alguns .md, .pdf ou .docx para deploy/sources, ou apontar KNOBRIDGE_SOURCES_DIR no .env), porque deploy/sources vem vazia e o chat responde melhor sobre um conteúdo que a pessoa conhece; os passos são conferidos de ponta a ponta numa stack limpa antes do commit"
    motivo: "menos contas e configuração para o primeiro uso; o README só promete o que foi executado"
    alternativas: "OpenAI como caminho principal; começar por um repositório Git; incluir documentos de exemplo no repositório"
    adr: null
pendencias_usuario: []
---

# Plano 0007 — README com início rápido

## 1. Pedido original

> "Prepare o readme.md para informar ao usuário de como utilizar o projeto de forma rápida e objetiva"

## 2. Entendimento (perguntas e respostas)

| # | Pergunta | Resposta | Data |
|---|---|---|---|
| 1 | Para quem é o início rápido? | Quem quer experimentar | 2026-10-12 |
| 2 | O que fazer com "Como testar"? | Mover para o fim, encolhida | 2026-10-12 |
| 3 | Experimentar sem chave paga (provedor `fake`)? | Não: direto com chave real | 2026-10-12 |

**O que será feito**: o `README.md` da raiz é reescrito, curto e objetivo, nesta ordem:

1. O que é, em duas ou três frases.
2. Requisitos: Docker com Compose v2 e uma chave do OpenRouter, ou da OpenAI.
3. **Início rápido** em passos numerados, cada um com o que clicar ou rodar e o que esperar:
   1. subir com `docker compose up -d --build --wait`;
   2. configuração inicial e e-mails no Mailpit;
   3. cadastrar o provedor com a chave;
   4. criar a coleção;
   5. colocar alguns documentos em `deploy/sources` (ou apontar `KNOBRIDGE_SOURCES_DIR` para uma pasta) e criar a fonte de pasta;
   6. criar o assistente ligado à coleção;
   7. perguntar no chat e ver a citação.
4. **Próximos passos**, uma linha e um link para cada guia: indexar um repositório Git, mapear código com o runner, receber chamados por API, "Abrir chamado".
5. **Parar e limpar** (`stop`, `down`, `down -v`).
6. **Problemas comuns** em três ou quatro linhas, com o link para o guia de subir o ambiente.
7. **Desenvolver**: uma linha por pacote com o comando dos gates, e os links para `AGENTS.md` e os READMEs dos pacotes.
8. **Onde ler mais**.

Os passos são executados de ponta a ponta numa stack limpa antes do commit, com a chave do OpenRouter do ensaio. Rótulos de tela, portas e comandos são conferidos no código e nos guias.

**Fora do escopo**: mudar guias, telas ou o compose. Se a conferência achar algo errado no produto, vira relato, não correção neste plano.

## 3. Critérios de aceite

- [ ] Uma pessoa com Docker e uma chave do OpenRouter chega a uma resposta com citação seguindo só o README.
- [ ] Os passos foram executados pelo orquestrador numa stack limpa; nomes de botões e campos batem com o painel.
- [ ] O README tem até cerca de 120 linhas, links relativos válidos e nenhuma afirmação de status desatualizada.
- [ ] Checagens de `AGENTS.md` e de planos verdes.

## 4. Fases e subfases

### F1 — README

#### F1.1 — Reescrever o README

- **Objetivo**: início rápido objetivo e conferido.
- **Entregáveis**: `README.md`.
- **Contexto necessário**: `README.md` atual; `docs/guias/subir-ambiente.md`, `primeiro-acesso.md` e `indexar-uma-fonte.md`; `.env.example` e `docker-compose.yml`; `deploy/sources/AGENTS.md`; textos do painel em `frontend/src/i18n/locales/pt-BR.json`.
- **Critérios de aceite**: os da seção 3.
- **Depende de**: nenhuma.
- **Tamanho**: pequeno.

## 5. Decisões

D1 vem das respostas do usuário; D2 é do agente.

## 6. Pendências do usuário

Nenhuma.

## 7. Registro de andamento

- 2026-10-12 — plano criado; aguardando aprovação.
- 2026-10-12 — plano aprovado pelo usuário ("Aprovado"); F1.1 iniciada: rascunho por agente em worktree, conferência de ponta a ponta pelo orquestrador.
- 2026-10-12 — F1.1 concluída: README reescrito (96 linhas) e conferido de ponta a ponta numa stack limpa com a chave do OpenRouter

## 8. Encerramento

**Entregue**: `README.md` da raiz reescrito (96 linhas) para quem quer experimentar: requisitos, início rápido em 9 passos com os nomes exatos das telas, próximos passos com links para os guias, parar e limpar, problemas comuns, uma seção curta de desenvolvimento e onde ler mais.

**Conferência**: os passos 2 a 9 foram executados pelo orquestrador numa stack limpa (projeto padrão, portas padrão) com a chave do OpenRouter. Resultados:

- documentos em `deploy/sources/manual`, ignorados pelo Git;
- `migrate` `Exited (0)`;
- superadmin, workspace e convite aceito pelo Mailpit;
- teste do provedor e da fonte ok;
- sincronização concluída;
- assistente com `openai/gpt-4.1-mini` e similaridade mínima de 0,35;
- resposta citando o documento certo;
- pergunta sem relação respondida "sem fonte".

Ajustes depois da conferência:

- o status agora diz que a Fase 0 do roadmap está concluída;
- o passo 1 ganhou uma nota para Windows.

Diferença do ambiente, que não vale para o usuário: a sub-rede padrão estava ocupada pela stack pausada do ensaio Minski, então a conferência subiu com outra `COMPOSE_SUBNET`.
