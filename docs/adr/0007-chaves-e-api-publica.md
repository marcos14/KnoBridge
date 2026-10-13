# ADR 0007 — Chaves de API e API pública

> Status: aceito · 2026-10-12 · plano 0008 (F1.1) · item 4 (escopo por assistente) e "modelo = assistente" substituídos pelo [ADR 0008](0008-produtos-e-niveis.md): escopo por produto com nível máximo e `model` = `<produto>[:<nível>]`

## Contexto

A [visão](../01-visao-do-projeto.md) promete suporte por **API REST** e por **API compatível com OpenAI** (seção 7.6 e decisão D14: "também Chat Completions"), com "API keys por workspace" e "sessão + API keys com escopo" (seção 7.7). Até o plano 0007, a única forma de conversar com um assistente era o painel, autenticado por sessão com cookie e CSRF ([ADR 0002](0002-sessao-server-side.md)). Integrar o KnoBridge em outro sistema, num script ou num cliente de chat como Open WebUI, LibreChat ou uma extensão de IDE exigia uma credencial que não fosse a sessão de uma pessoa.

O [plano 0008](../planos/0008-telas-de-uso-e-administracao.md) registra a escolha do usuário (D3): chaves por workspace, mostradas uma vez e com escopo opcional por assistente, abrindo uma REST própria de conversa e as rotas `/v1/models` e `/v1/chat/completions`, com cada assistente como um "modelo", streaming SSE e citações num campo extra. Faltava decidir o formato e a verificação da chave, o isolamento entre workspaces e o que a chave abre (D6). O contrato está em [api-publica.md](../specs/api-publica.md).

## Decisão

1. **Chave de API por workspace, no padrão dos tokens de runner e de envio** (D6). Formato `kbk_<prefixo>_<segredo>`: prefixo de 8 caracteres `[a-z0-9]`, único na instância e guardado em claro; segredo de 32 bytes aleatórios em base64url. O servidor guarda só o SHA-256 do token inteiro. A chave aparece uma única vez, na criação. É o terceiro uso do mesmo padrão ([runner.md](../specs/runner.md#token-de-runner), [chamados.md](../specs/chamados.md#token-de-envio)).
2. **Verificação por prefixo em modo de sistema, depois escopo do workspace.** A dependência busca a chave pelo prefixo, compara o hash em tempo constante e abre a transação com `SET LOCAL app.workspace_id` do workspace da chave. Daí em diante, a RLS isola como em qualquer rota de workspace ([ADR 0001](0001-tenancy-e-rls.md)). O `workspace_id` nunca vem do cliente (regra do `AGENTS.md` raiz, seção 10).
3. **Uma resposta só para chave ruim**: ausente, malformada, desconhecida, com hash diferente ou revogada dá o mesmo 401. A revogação vale na próxima requisição. A chave nunca vai para log nem para a auditoria; só o prefixo.
4. **Escopo opcional por assistente.** Sem escopo, a chave fala com todos os assistentes ativos do workspace. Com escopo, só com os listados. Assistente fora do escopo é tratado como inexistente.
5. **A chave abre só a API pública** (`/v1/models`, `/v1/chat/completions` e `/v1/conversations…`). Ela não abre rotas do painel, e a sessão do painel não abre a API pública. As rotas da API pública não leem cookie nem exigem CSRF.
6. **Criar, editar e revogar exigem owner ou admin**, com auditoria. É uma credencial, como os tokens de runner e de envio. O uso da chave não é auditado por requisição; a chave guarda `last_used_at`.
7. **Conversas da API pertencem à chave, não a uma pessoa.** Elas ficam gravadas como as do painel, com `channel = api`, e aparecem na visão administrativa de conversas. Cada resposta registra o canal e o custo estimado (D4, D7 do plano).
8. **A API compatível com OpenAI é sem estado, como a original.** Cada chamada a `/v1/chat/completions` vira uma conversa nova com a última pergunta e a resposta. O histórico enviado pelo cliente vai ao LLM como contexto, mas não é gravado. A busca usa só a última mensagem do usuário. A regra 8 vale igual: sem fonte, o LLM não é chamado e a resposta é a mensagem de "sem fonte" do assistente.

## Alternativas consideradas

- **OAuth 2.0 client credentials**: padrão para integração entre serviços, mas exige servidor de autorização, emissão e renovação de tokens de acesso e mais uma tela, para o mesmo efeito de uma chave revogável. Clientes OpenAI só enviam `Authorization: Bearer <chave>` fixa. Descartada (D6).
- **Chave por usuário** (herdando o papel da pessoa): amarraria a integração a uma conta, que pode sair do workspace ou ser suspensa e derrubar a integração. Misturaria auditoria de pessoa com tráfego de sistema. Descartada (D6).
- **Só a API compatível com OpenAI, ou só a REST própria**: a compatível cobre clientes de chat prontos, mas não dá id de conversa nem leitura posterior; a REST própria cobre integrações com estado, mas exige adaptador em cada cliente de chat. O usuário escolheu as duas (D3).
- **Guardar a chave cifrada** (como as chaves de provedores, [ADR 0003](0003-segredos-cifrados.md)): permitiria mostrá-la de novo, mas o servidor não precisa dela em claro, só de comparar. Hash basta e vaza menos.
- **Gravar o histórico inteiro de cada chamada OpenAI**: cada turno de um cliente de chat reenvia toda a conversa, e gravar tudo duplicaria as mensagens a cada chamada. Grava-se só a pergunta e a resposta da chamada.
- **Limite de requisições e cotas por chave**: fora do escopo deste lote (seção 2 do plano). A instância continua protegida pelo limite de corpo e pelos limites dos provedores.

## Consequências

- Tabela nova `api_keys` (workspace, nome, prefixo único na instância, hash, escopo, quem criou, `last_used_at`, `revoked_at`) com RLS forçada. `conversations` passa a aceitar dono do tipo chave (`api_key_id`, `user_id` nulo) e `channel = api`; `messages` ganha `channel` e `cost_usd`. Modelo físico em [modelo-de-dados.md](../specs/modelo-de-dados.md), na migração do plano.
- O prefixo fixo `kbk_` permite que varreduras de segredos (gitleaks e similares) reconheçam a chave, como `kbr_` e `kbi_`.
- Os erros de `/v1/models` e `/v1/chat/completions` seguem o formato da OpenAI (`{"error": {"message", "type", "param", "code"}}`), para os SDKs oficiais tratarem. As demais rotas, inclusive a REST própria de conversa, mantêm o formato único do KnoBridge.
- O "modelo" de um cliente OpenAI é o nome do assistente (ou o id dele). Renomear um assistente quebra os clientes configurados pelo nome; o id é estável.
- Parâmetros de geração do cliente (`temperature`, `max_tokens`...) são ignorados: quem decide é a configuração do assistente. Isso mantém a regra de citações sob controle do servidor.
- Sem limite por chave, uma chave vazada consome provedor até ser revogada. A tela mostra o último uso de cada chave para ajudar a perceber abuso.
