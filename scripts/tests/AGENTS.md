# scripts/tests/

**Função**: testes `pytest` dos scripts de `scripts/`.

**Entra aqui**: um `test_<script>.py` por script, com testes `test_<unidade>_<comportamento>` em arrange / act / assert, um comportamento por teste.
**Não entra aqui**: testes do backend (`backend/tests/`) ou do frontend; dados reais de qualquer tipo.

**Convenções locais**:
- Árvores de pastas e planos são construídos em `tmp_path` dentro do próprio teste; não há fixtures em disco.
- Testes que dependem do repositório real levam `@pytest.mark.repo`.
- Testes que precisam do executável `git` são pulados quando ele não existe; nunca dependem de rede.
- `test_synthetic_tickets.py`: determinismo por semente, campos e instantes dos chamados, gabarito apontando para o texto que contém cada valor, CPF/CNPJ/Luhn/telefone válidos, artigos e perguntas, CLI; o teste `repo` confere que o JSONL do E2E é a saída do gerador (semente 1, 4 chamados).
- `test_webhook_sink.py`: assinatura (aceita, corpo ou segredo trocados, `t` velho), rotas do receptor falso chamadas direto e um servidor HTTP local em `127.0.0.1` porta 0, parado no fim do teste.

**Como testar**: de dentro de `scripts/`, `uv run pytest` (gate de 95% de linhas e branches).

**Leia também**: [scripts/AGENTS.md](../AGENTS.md); seção 5 do [AGENTS.md da raiz](../../AGENTS.md).
