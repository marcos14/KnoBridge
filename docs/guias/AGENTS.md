# docs/guias/

**Função**: guias de operação do KnoBridge, passo a passo, para quem vai subir, configurar ou operar a plataforma.

**Entra aqui**:
- `subir-ambiente.md`: subir o ambiente de desenvolvimento completo com Docker Compose.
- Futuramente: conectar Slack ou Google Chat, rodar o harness de código, criar um conector, operar backups.

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
