# docs/guias/

**Função**: guias de operação do KnoBridge, passo a passo, para quem vai subir, configurar ou operar a plataforma.

**Entra aqui**:
- `subir-ambiente.md`: subir o ambiente de desenvolvimento completo com Docker Compose.
- `primeiro-acesso.md`: da instância vazia ao primeiro chat: superadmin, workspace, convites, provedor (`fake` em dev ou real) e assistente, com os e-mails lidos no Mailpit.
- `indexar-uma-fonte.md`: da pasta montada em `/sources` (ou da URL de um repositório) às respostas com citação: provedor com embeddings (OpenRouter), coleção, fonte Git ou de pasta, sincronização, execuções e erros, teste de busca, coleção ligada ao assistente e problemas comuns.
- `mapear-codigo-com-runner.md`: do checkout local ao conhecimento citado no chat: criar o runner no painel, instalar, `configure`, `doctor`, login de assinatura x chave de API, `run`, fonte runner, módulos, tarefas, revisão e exportação, segurança (somente leitura, trava de ferramenta, ambiente filtrado), o que sai da máquina e custos.
- Futuramente: conectar Slack ou Google Chat, criar um conector, operar backups.

**Não entra aqui**:
- Contratos (API, modelo de dados, protocolos): `docs/specs/`.
- Decisões de arquitetura: `docs/adr/`.
- Arquivos de infraestrutura (compose, Helm): `deploy/`.
- Segredos reais, URLs internas de clientes, dados reais.

**Convenções locais**:
- Um guia por tarefa, nome em kebab-case com verbo (`subir-ambiente.md`, `conectar-slack.md`).
- Estrutura: pré-requisitos, passos numerados com comandos copiáveis, como verificar, como desfazer, problemas comuns.
- Comandos rodam a partir da raiz do repositório, salvo quando o guia disser outra coisa.
- Guia muda na mesma entrega que o comportamento que ele descreve (ex.: serviço ou porta nova no compose).

**Como testar**: não há teste automatizado. Antes de entregar, execute os comandos do guia num ambiente limpo e confira links relativos.

**Leia também**: [docs/AGENTS.md](../AGENTS.md); [deploy/AGENTS.md](../../deploy/AGENTS.md).
