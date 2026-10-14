# docs/guias/

**Função**: guias de operação do KnoBridge, passo a passo, para quem vai subir, configurar ou operar a plataforma.

**Entra aqui**:
- `subir-ambiente.md`: subir o ambiente de desenvolvimento completo com Docker Compose.
- `primeiro-acesso.md`: da instância vazia ao primeiro chat: superadmin e primeiro workspace na configuração inicial, Início com os primeiros passos, painel da instância, outros workspaces e "Entrar" do superadmin, convites (com nível por produto), provedor (`fake` em dev ou real), níveis de resposta, produto, chat com produto e nível e Uso e custos, com os e-mails lidos no Mailpit.
- `produtos-e-niveis.md`: produtos e níveis de resposta: os três níveis, configuração (credencial, modelo, temperatura, instruções e custo por resposta), produtos, nível máximo por membro e no convite, nível mínimo das fontes e o refinamento automático, chat por nível, API com `produto:nível`, workspaces que tinham assistentes e problemas comuns.
- `usar-a-api.md`: chamar os produtos de outro sistema: chave de API no painel, escopo por produto e nível máximo, `GET /v1/models` com `produto:nível`, REST de conversa com `product_id` e `level` (JSON e SSE), API compatível com OpenAI em `curl`, Python e JavaScript com o SDK oficial (citações no campo `knobridge`, rodapé de fontes), uso e custo por canal e chave, limites, erros comuns (inclusive `level_not_allowed`), revogação e integrações anteriores à v0.2 (`assistant_id`, nome do assistente).
- `indexar-uma-fonte.md`: da pasta montada em `/sources` (ou da URL de um repositório) às respostas com citação: provedor com embeddings (OpenRouter), coleção, fonte Git ou de pasta, sincronização, execuções e erros, teste de busca, coleção ligada ao produto e problemas comuns.
- `mapear-codigo-com-runner.md`: do checkout local ao conhecimento citado no chat: criar o runner no painel, instalar, `configure`, `doctor`, login de assinatura x chave de API, `run`, fonte runner, módulos, tarefas, revisão e exportação, segurança (somente leitura, trava de ferramenta, ambiente filtrado), o que sai da máquina e custos.
- `receber-chamados-por-api.md`: integrar um sistema de chamados: fonte e token de envio, formato, envio por `curl`, Python e n8n (lote, remoção, reenvio idempotente, resultado por item), carga histórica por upload, prévia e anonimização, e o webhook "Abrir chamado" do produto, do lado do receptor (assinatura em Python e Node, resposta `{ticket_id, url}`, retentativas), limites e erros comuns.
- `receber-cards-por-api.md`: integrar uma ferramenta de cards de desenvolvimento pelo mesmo caminho dos chamados: fonte de cards e nível mínimo, token, formato do card, envio por `/v1/ingest/cards`, upload e prévia, citação no nível Desenvolvimento e produto e o que difere dos chamados.
- `conectar-pelo-mcp.md`: os produtos como ferramentas do Claude Code, do Cursor e do Codex pelo servidor MCP (`/v1/mcp`): chave com nível máximo, variável `KNOBRIDGE_API_KEY`, configuração de cada cliente, as cinco ferramentas, níveis, onde aparece no painel e problemas comuns (401, Host, `Origin`, 405, níveis).
- `embutir-o-widget.md`: o chat de um produto num site ou sistema: criar o widget, domínios permitidos, instalar com uma linha de `<script>`, site de teste local, aparência (atributos, variáveis CSS, métodos), modo embutido, identidade assinada com exemplos em Python e Node, acompanhamento, limites, privacidade e problemas comuns.
- Futuramente: conectar Slack ou Google Chat, criar um conector, operar backups.

**Não entra aqui**:
- Contratos (API, modelo de dados, protocolos): `docs/specs/`.
- Decisões de arquitetura: `docs/adr/`.
- Arquivos de infraestrutura: o compose na raiz do repositório; Helm e scripts de infra em `deploy/`.
- Segredos reais, URLs internas de clientes, dados reais.

**Convenções locais**:
- Um guia por tarefa, nome em kebab-case com verbo (`subir-ambiente.md`, `conectar-slack.md`).
- Estrutura: pré-requisitos, passos numerados com comandos copiáveis, como verificar, como desfazer, problemas comuns.
- Comandos rodam a partir da raiz do repositório, salvo quando o guia disser outra coisa.
- Guia muda na mesma entrega que o comportamento que ele descreve (ex.: serviço ou porta nova no compose).

**Como testar**: não há teste automatizado. Antes de entregar, execute os comandos do guia num ambiente limpo e confira links relativos.

**Leia também**: [docs/AGENTS.md](../AGENTS.md); [deploy/AGENTS.md](../../deploy/AGENTS.md).
