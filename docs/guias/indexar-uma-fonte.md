# Indexar uma fonte: de uma pasta ou repositório às respostas com citação

> Rascunho v0.1 · 2026-10-11 · Em uso (plano 0003)

Passo a passo pelo painel para pôr conhecimento no KnoBridge: montar a pasta de fontes, cadastrar um provedor com embeddings (OpenRouter), criar uma coleção, cadastrar uma fonte Git ou de pasta, sincronizar, acompanhar as execuções, testar a busca e ligar a coleção a um produto, até ver as citações no chat.

Para gerar conhecimento a partir do código com o Claude Code ou o Codex, rodando na máquina que tem o checkout (fonte do tipo **Runner local**), siga [mapear-codigo-com-runner.md](mapear-codigo-com-runner.md). Para trazer chamados de um sistema de chamados (fonte do tipo **Chamados**, por API ou upload), siga [receber-chamados-por-api.md](receber-chamados-por-api.md); para cards de desenvolvimento, [receber-cards-por-api.md](receber-cards-por-api.md). A coleção e o produto são os mesmos deste guia. O nível mínimo de cada fonte (quem recebe os trechos dela no chat) está em [produtos-e-niveis.md](produtos-e-niveis.md#4-ajustar-o-nível-mínimo-das-fontes).

Como funciona por dentro: leitura das fontes em [conectores.md](../specs/conectores.md), indexação e busca em [indexacao.md](../specs/indexacao.md), chat em [chat.md](../specs/chat.md).

## Pré-requisitos

- Ambiente rodando e saudável, conforme [subir-ambiente.md](subir-ambiente.md), e um workspace com você como owner, admin ou editor, conforme [primeiro-acesso.md](primeiro-acesso.md). Leitores veem fontes e coleções e podem testar a busca, mas não criam nem sincronizam.
- Para embeddings reais: uma chave do [OpenRouter](https://openrouter.ai/) (ou da OpenAI). Em desenvolvimento, sem chave, o provedor `fake` também gera embeddings (determinísticos, por palavras em comum, bons só para testar o fluxo).
- O material a indexar: uma pasta de documentos ou um clone Git, na sua máquina; ou a URL https de um repositório público.

Nunca use dados reais de clientes num ambiente de desenvolvimento compartilhado.

## Passos

### 1. Montar a pasta de fontes

Fontes de pasta e repositórios Git locais são lidos de uma pasta do host, montada **somente leitura** em `/sources` na `api` (para "Testar conexão") e no `worker` (que indexa). O padrão é `deploy/sources/`, ignorada pelo Git. Detalhes em [subir-ambiente.md](subir-ambiente.md#pasta-de-fontes).

1. Copie a pasta ou clone o repositório para dentro dela:

   ```bash
   cp -r ~/documentos/manual-do-sistema deploy/sources/manual
   git clone https://github.com/<org>/<repo>.git deploy/sources/meu-repo
   ```

   Ou aponte `KNOBRIDGE_SOURCES_DIR` no `.env` da raiz para outra pasta do host (caminho absoluto, ou relativo à raiz do repositório).

2. Se mudou `KNOBRIDGE_SOURCES_DIR`, recrie `api` e `worker`:

   ```bash
   docker compose up -d --wait
   ```

3. Confira o que o worker enxerga:

   ```bash
   docker compose exec worker ls /sources
   ```

No painel, o caminho é sempre o de **dentro** do contêiner: `/sources/manual`, `/sources/meu-repo`. Cadastre a subpasta, nunca a raiz `/sources`. Repositórios por URL https não usam essa pasta: o worker os clona no volume `source-clones`.

### 2. Cadastrar um provedor com embeddings

1. Vá em **Provedores > Novo provedor**.
2. Preencha:
   - **Tipo**: `OpenRouter`;
   - **Nome**: por exemplo, `OpenRouter`;
   - **URL base (opcional)**: em branco. O padrão já é `https://openrouter.ai/api/v1`; preencha só se usar um proxy;
   - **Chave de API**: a sua chave do OpenRouter.
3. Clique em **Salvar** e depois em **Testar conexão**.

A chave é cifrada ao salvar e nunca volta para a tela; só os 4 últimos caracteres aparecem ([ADR 0003](../adr/0003-segredos-cifrados.md)). A mesma credencial serve para os embeddings da coleção e para o modelo de chat dos níveis de resposta.

Alternativas:

- **OpenAI direta**: tipo `OpenAI`. O modelo de embedding fica sem prefixo (`text-embedding-3-small`).
- **Desenvolvimento sem chave**: tipo `Fake (testes, sem rede)`, chave qualquer com 8 caracteres ou mais. Só funciona fora de produção.
- **Anthropic** não serve para a coleção: não oferece embeddings.

### 3. Criar uma coleção

A coleção guarda os trechos indexados e define o modelo de embedding usado na indexação e na busca.

1. Vá em **Coleções > Nova coleção**.
2. Preencha:
   - **Nome**: por exemplo, `Documentação do ERP`;
   - **Descrição** (opcional);
   - **Credencial de embedding**: a do passo 2;
   - **Modelo de embedding**: `openai/text-embedding-3-small`. É o padrão sugerido para OpenRouter; na OpenAI direta, `text-embedding-3-small`.
3. Clique em **Salvar**.

O índice guarda vetores de 1536 dimensões, o tamanho do `text-embedding-3-small`. **Depois que a coleção tiver documentos, credencial e modelo não mudam mais**: para usar outro modelo, crie outra coleção e cadastre as fontes nela.

### 4. Cadastrar a fonte

1. Vá em **Fontes > Nova fonte** e preencha **Nome**, **Coleção** (a do passo 3) e **Tipo**. Coleção e tipo não mudam depois.
2. Conforme o tipo:
   - **Repositório Git**:
     - **Onde está o repositório**: `Clone no servidor`, com o **Caminho do clone** (ex.: `/sources/meu-repo`, a raiz do repositório), ou `URL pública (https)`, com a **URL do repositório** (sem usuário nem senha);
     - **Branch (opcional)**: em branco, a branch padrão;
     - **Commits indexados na primeira sincronização**: padrão 200, de 0 a 5000. Os commits mais recentes viram documentos, com mensagem, autor (só o nome) e arquivos alterados; depois, cada sincronização indexa os commits novos.
   - **Pasta**: **Caminho da pasta** (ex.: `/sources/manual`).
   - **Runner local**: o harness de código na máquina com o checkout; passo a passo em [mapear-codigo-com-runner.md](mapear-codigo-com-runner.md).
3. **Incluir** e **Excluir** (opcionais): um padrão por linha, na sintaxe do `.gitignore`, relativos à raiz da fonte. Em branco, entra tudo que passa pelas regras padrão. Exemplos:
   - incluir `docs/**` e `*.md`;
   - excluir `**/testes/**` e `docs/rascunhos/**`.

   Mesmo sem globs, ficam de fora `.git`, `node_modules`, `dist`, `build`, `vendor`, o que o `.gitignore` ignora, lockfiles, binários (imagens, arquivos compactados, executáveis) e arquivos acima de 2 MiB. PDF, DOCX, XLSX e PPTX entram, até 20 MiB. Regras completas em [conectores.md](../specs/conectores.md#seleção-de-arquivos).
4. Para sincronizar sozinho, marque **Sincronizar automaticamente** e escolha um agendamento pronto ou digite um cron de cinco campos, **sempre em UTC**. Exemplos:
   - `0 3 * * *`: todo dia às 3h UTC, ou meia-noite em Brasília;
   - `0 */6 * * *`: a cada 6 horas.

   Desmarcado, o agendamento fica pausado e só a sincronização manual roda.
5. Deixe **Ativa** marcada e clique em **Salvar**.

### 5. Testar a conexão

Clique no nome da fonte para abrir o detalhe e use **Testar conexão**. Deve aparecer "A fonte ... está acessível.". Se falhar, a mensagem diz o motivo (veja [Problemas comuns](#problemas-comuns)).

### 6. Sincronizar e acompanhar

1. Clique em **Sincronizar agora**. A execução entra **Na fila**, passa a **Em execução** e termina **Concluída**, **Falhou** ou **Cancelada**. A tela se atualiza sozinha enquanto há execução ativa.
2. Em **Execuções**, cada linha mostra:
   - gatilho (manual ou agendada) e início;
   - documentos novos, alterados, removidos e com erro;
   - trechos gravados, tokens de embedding, custo estimado em USD e duração.
3. **Ver erros** mostra a falha geral da execução, se houve, e os documentos que falharam, com a etapa (leitura ou análise), o código e a mensagem. Um documento com erro não derruba a execução: os demais são indexados.
4. Em **Documentos indexados**, busque por caminho e filtre por arquivos ou commits para conferir o que entrou e quantos trechos cada um gerou.
5. Para interromper, use **Cancelar sincronização**. O cursor da fonte só avança quando a execução termina com sucesso, então a próxima retoma de onde a última concluída parou, sem pagar de novo pelo que já foi gravado.

A segunda sincronização é **incremental**:

- na pasta, só os arquivos cujo conteúdo mudou;
- no Git, só os arquivos alterados entre o commit indexado e o HEAD atual, mais os commits novos.

Arquivos sem mudança não chamam o provedor de embedding e não custam nada.

Pela linha de comando, o andamento aparece no log do worker:

```bash
docker compose logs -f worker
```

O histórico do workflow `ingestion-<id da fonte>` fica na Temporal UI (<http://localhost:8080>, porta padrão).

### 7. Testar a busca

1. Vá em **Coleções**, abra a coleção e use **Testar busca**.
2. Digite uma pergunta ou termos (nomes de função e caminhos também funcionam) e clique em **Buscar**.
3. Cada resultado mostra:
   - o documento, o caminho com as linhas ou o commit;
   - o símbolo e a linguagem, em código;
   - as pontuações: fusão, vetorial e texto;
   - o trecho.

Um trecho entra quando a similaridade vetorial alcança o limiar (padrão 0,35, calibrado pelo [ensaio com dados reais](../pesquisa/0001-ensaio-minski.md)) **ou** quando ele contém todos os termos da busca. Nada é gravado. Use esta tela para calibrar a **Similaridade mínima** antes de ligar a coleção ao produto: se perguntas relacionadas voltam vazias, baixe o limiar; se aparecem trechos sem relação, suba.

### 8. Ligar a coleção ao produto

1. Para usar o OpenRouter também no chat, em **Configurações > Níveis de resposta** escolha a credencial do passo 2 em **Credencial** de cada nível e informe em **Modelo** o identificador do OpenRouter (com o prefixo do fornecedor, ex.: `openai/gpt-4.1-mini`); detalhes em [produtos-e-niveis.md](produtos-e-niveis.md#1-configurar-os-níveis-de-resposta).
2. Vá em **Produtos** e edite (ou crie) o produto. Em **Coleções**, marque a coleção do passo 3. Um produto pode consultar várias coleções.
3. Ajuste **Similaridade mínima** com o que você viu no passo 7. Em branco, vale o padrão do modelo de embedding de cada coleção (0,35 no `text-embedding-3-small`), e a edição do produto mostra o limiar em uso por modelo.
4. Clique em **Salvar**.

Sem nenhuma coleção marcada, o produto responde sempre "sem fonte".

### 9. Conversar e ler as citações

1. Vá em **Chat**, escolha o produto e o nível e faça uma pergunta sobre o conteúdo indexado. Numa pasta, arquivos de código só aparecem no nível **Desenvolvimento e produto**.
2. A resposta chega em streaming, com marcadores `[1]`, `[2]`... que apontam para as **Fontes** listadas abaixo dela.
3. Clique numa fonte para ver:
   - o trecho usado;
   - o arquivo e as linhas, o símbolo e a linguagem, para código e texto;
   - o SHA, o autor e a data, para commits.
4. Pergunte algo sem relação com o conteúdo: a resposta deve ser a mensagem de "sem fonte", sem chamar o LLM. É a regra do produto: resposta sem fonte não existe.

## Como verificar

- **Coleções** mostra, por coleção, a quantidade de fontes, documentos e trechos.
- A execução da fonte termina **Concluída**, com documentos novos e trechos maiores que zero. Uma segunda sincronização sem mudanças na fonte termina com zero documentos novos e zero tokens.
- **Testar busca** devolve trechos do material para uma pergunta relacionada e volta vazio para uma sem relação.
- Se poucos arquivos ou um diretório ocuparem uma parte desproporcional dos trechos (relatórios gerados, código minificado), a lista de fontes mostra o selo "… dominam o índice" e o detalhe da fonte, a seção **Arquivos que dominam o índice**, com a participação de cada grupo e o padrão sugerido. Quem edita a fonte clica em **Excluir** para acrescentar o padrão às exclusões e depois em **Sincronizar agora**: os trechos saem do índice.
- **Auditoria** (owner/admin) registra a criação da coleção, da fonte e as sincronizações pedidas.

## Como desfazer

- **Excluir a fonte** (em **Fontes**) apaga, sem volta, os documentos e trechos dela e cancela a sincronização em andamento. Os arquivos em `/sources` nunca são tocados: a montagem é somente leitura.
- **Excluir a coleção** só funciona depois de excluir as fontes dela.
- **Excluir a credencial** só funciona quando nenhuma coleção nem nível de resposta a usa.
- **Pausar sem excluir**: desmarque **Sincronizar automaticamente** ou **Ativa** na fonte.

## Problemas comuns

- **"O caminho está fora da pasta liberada para fontes locais"** (`path_outside_root`): o caminho cadastrado tem de estar abaixo de `/sources`, visto de dentro do contêiner, e não pode escapar dela por `..` ou por um symlink que aponte para fora. Use `/sources/<subpasta>`, nunca o caminho do host (`C:\...` ou `/home/...`). Num worktree Git ligado, o repositório principal também precisa estar dentro de `/sources`.
- **"Não foi possível ler a fonte"** (`source_unavailable`) numa pasta ou num clone montado. Causas comuns:
  - a pasta não existe no contêiner: confira com `docker compose exec worker ls /sources/<subpasta>` e, se mudou `KNOBRIDGE_SOURCES_DIR`, recrie `api` e `worker`. No Windows, a pasta precisa estar num disco compartilhado com o Docker Desktop;
  - num repositório Git, o caminho não é a raiz do clone (uma subpasta é recusada) ou a pasta não é um repositório.
- **Repositório com outro dono / `safe.directory`**: a pasta montada costuma ter outro dono que o usuário do worker, e o git recusa esses repositórios ("dubious ownership"). O KnoBridge passa `-c safe.directory=<caminho>` só para o caminho cadastrado, então a indexação funciona sem configurar nada. Para inspecionar o repositório à mão dentro do contêiner, faça o mesmo:

  ```bash
  docker compose exec worker \
    git -c safe.directory=/sources/meu-repo -C /sources/meu-repo log -1 --oneline
  ```

- **"O branch configurado não existe no repositório"** (`branch_not_found`): confira o nome. Num clone local, a branch pode existir só como `origin/<branch>`, o que também serve; se nem isso existir, rode `git fetch` no clone do host.
- **Não aparece credencial para a coleção, ou "Este provedor não oferece embeddings"**: a credencial é da Anthropic, que não tem embeddings. Cadastre uma do OpenRouter ou da OpenAI para a coleção; os níveis de resposta podem continuar usando a Anthropic no chat.
- **"A coleção já tem documentos: o provedor e o modelo de embedding não podem mudar"** (`collection_embedding_locked`): a troca de modelo é travada para o índice não misturar vetores de modelos diferentes. Crie outra coleção com o modelo novo, cadastre as fontes nela, sincronize e troque a coleção no produto. Depois, exclua as fontes antigas e a coleção antiga.
- **"O modelo de embedding devolveu vetores de tamanho diferente do índice"** (`embedding_dimension_mismatch`): o modelo não gera 1536 dimensões. Use `openai/text-embedding-3-small` (OpenRouter) ou `text-embedding-3-small` (OpenAI).
- **A execução falhou com `provider_auth_failed` ou `provider_request_failed`**: chave recusada ou modelo inexistente no provedor. Teste a credencial em **Provedores** e confira o nome do modelo, com o prefixo do fornecedor no OpenRouter. Indisponibilidade e limite de uso do provedor são repetidos automaticamente (até 5 tentativas) antes de falhar.
- **"O serviço de sincronização está indisponível"** (`sync_unavailable`): o Temporal não respondeu. Confira `docker compose ps temporal worker`. Fontes salvas nesse meio tempo têm o agendamento acertado quando o worker sobe de novo.
- **"Esta fonte já está sincronizando"**: só uma execução por fonte roda de cada vez. Espere terminar ou cancele. Disparos agendados nesse meio tempo são pulados sem erro.
- **Um arquivo não foi indexado**: veja se ele é ignorado pelo `.gitignore`, pelos globs, pelo tamanho (2 MiB para texto, 20 MiB para PDF/Office) ou por ser binário. No Git, só entra o que está commitado na branch: mudanças locais não commitadas não aparecem.
- **O chat responde "sem fonte" para uma pergunta que deveria ter resposta**: confira se a coleção está marcada no produto, se a execução concluiu, se **Testar busca** encontra trechos e se o nível da conversa alcança o nível mínimo da fonte (código e chamados não chegam ao Usuário final). Se só aparecerem trechos com pontuação vetorial abaixo do limiar, baixe a **Similaridade mínima** do produto.

## Referências

- OpenRouter (modelos e chaves): <https://openrouter.ai/docs>
- Modelos de embedding da OpenAI: <https://platform.openai.com/docs/guides/embeddings>
- Formato dos padrões do `.gitignore`: <https://git-scm.com/docs/gitignore>
- `safe.directory`: <https://git-scm.com/docs/git-config#Documentation/git-config.txt-safedirectory>
- Sintaxe cron: <https://crontab.guru/>
