# ADR 0011 — Reranker opcional e desligado por padrão

> Status: aceito · 2026-10-17 · plano 0011 (F4.3) · substitui em parte o [ADR 0010](0010-busca-em-etapas-e-reranker.md) (itens 1 e 3: serviço sempre ligado e reordenação ligada por padrão)

## Contexto

O [ADR 0010](0010-busca-em-etapas-e-reranker.md) pôs o reranker `BAAI/bge-reranker-v2-m3`, servido pelo Text Embeddings Inference (TEI) em CPU, como serviço **sempre ligado** do compose (decisão D2 do [plano 0011](../planos/0011-qualidade-da-resposta.md)), com `KNOBRIDGE_RERANKER_URL` definida por padrão e a opção **Reordenar trechos** ligada em todo produto (D3). A previsão era de "um a alguns segundos" para reordenar 30 trechos, com teto no timeout de 10 s.

O ensaio da F4.3, com dados reais numa máquina de 16 CPUs, mediu outra coisa:

- **Latência.** Na revisão fixada do modelo não há pesos ONNX, então a imagem de CPU do TEI usa o backend candle. Reordenar 30 trechos de 900 caracteres levou **34 s**; 30 trechos de 2.000 caracteres (o `KNOBRIDGE_RERANKER_MAX_CHARS` padrão), **96 s**. As duas medidas passam muito do timeout de 10 s: na prática, cada busca esperava 10 s e caía na ordem do RRF, e a busca em etapas pagava essa espera a cada etapa.
- **Memória.** Com o limite de 4 GB, o contêiner era morto por falta de memória ainda no aquecimento, mesmo com `--max-batch-tokens 2048` (o comentário do compose dizia o contrário). Ele precisa de cerca de **6 a 8 GB**.
- **Custo de subir.** A primeira subida baixava cerca de 2,3 GB de modelo e o `docker compose up --wait` esperava até 15 minutos por ele, para um serviço que, com os padrões, não chegava a reordenar nada.

## Decisão

Decisão D25 do plano 0011, do usuário:

1. **O serviço `reranker` sai do `docker compose up` padrão** e fica atrás do perfil `reranker` do compose (`profiles: [reranker]`). Sobe com `docker compose --profile reranker up -d` (ou `COMPOSE_PROFILES=reranker`).
2. **`KNOBRIDGE_RERANKER_URL` fica vazia por padrão** no compose e no `.env.example`: a instância não tem reranker e as buscas seguem na ordem do RRF, como antes do plano 0011. Ligar é definir `http://reranker:80` e usar o perfil.
3. **`mem_limit` do serviço passa a `${RERANKER_MEMORY_LIMIT:-8g}`**, mantendo `--max-batch-tokens 2048` (que limita o aquecimento, mas não o faz caber em 4 GB).
4. **Produtos novos nascem com `rerank: false`**: na API, no serviço, no ORM e no banco (migração `0025`, padrão `false` em `products.rerank`). Os produtos existentes ficam com o valor que tinham; sem reranker na instância, `rerank_available` é falso e nada muda para eles.
5. **A camada de E2E mantém o reranker falso sempre ligado**: `docker-compose.e2e.yml` tira o perfil do serviço (`profiles: !reset []`) e define `KNOBRIDGE_RERANKER_URL=http://reranker:80` na `api`. O E2E da qualidade liga a reordenação no produto explicitamente.
6. **O painel explica a ausência**: com `rerank_available` falso, "Reordenar trechos" aparece desabilitado com o texto de que a instância não tem reranker (opcional, desligado por padrão) e a indicação do guia [subir-ambiente.md](../guias/subir-ambiente.md#reranker).

Nada muda no contrato do reranker ([indexacao.md](../specs/indexacao.md#reranker)), no cliente, na queda para a ordem do RRF nem no "Testar busca": quem ligar o serviço tem o comportamento do ADR 0010.

## Alternativas consideradas

- **Um cross-encoder multilíngue menor com ONNX** (por exemplo um mMiniLM): rodaria em CPU em uma fração do tempo e da memória. Fica para um plano futuro, que depende do ganho de qualidade medido no ensaio: só vale trocar o modelo se a reordenação mostrar ganho que justifique o serviço.
- **Reordenar só 10 trechos curtos** (`KNOBRIDGE_RERANKER_CANDIDATES` e `KNOBRIDGE_RERANKER_MAX_CHARS` menores, mantendo o serviço ligado): ainda cerca de **11 s** por busca e os mesmos 6 a 8 GB, sem ganho que pague isso. Descartada.
- **Manter o serviço sempre ligado só com mais memória e timeout maior**: toda instância pagaria 6 a 8 GB e respostas dezenas de segundos mais lentas por padrão. Descartada pelo usuário.
- **Remover o reranker do compose**: perderia o caminho pronto para quem tem máquina para ele (ou GPU, com outra imagem) e o "Testar busca" para comparar. Descartada: o perfil deixa o serviço disponível sem custo para quem não o liga.

## Consequências

- A instalação padrão volta aos requisitos de antes do plano 0011 (cerca de 4 GB de RAM, sem download de modelo) e o `up --wait` não espera mais o reranker.
- Sem reranker, a qualidade da ordem é a da busca híbrida com RRF; a busca em etapas e o limiar por modelo, do mesmo plano, seguem valendo.
- Quem liga o reranker em CPU aceita buscas dezenas de segundos mais lentas (ou a espera do timeout com queda para o RRF) e 6 a 8 GB de memória. O guia [subir-ambiente.md](../guias/subir-ambiente.md#reranker) traz as medidas e como ligar e desligar.
- Migração `0025` ([modelo-de-dados.md](../specs/modelo-de-dados.md#migrações)): padrão de `products.rerank` no banco passa a `false`; o `downgrade` volta a `true`.
- Contrato aditivo para a API: `rerank` omitido no `POST` de produto passa a gravar `false`.
- Substitui as decisões D2 (sempre ligado) e, para produtos novos, D3 (ligada por padrão) do plano 0011 e os itens correspondentes do ADR 0010, que ganhou a indicação no status.

## Referências

- Text Embeddings Inference (backends candle e ONNX, imagens de CPU): <https://github.com/huggingface/text-embeddings-inference>
- `BAAI/bge-reranker-v2-m3`: <https://huggingface.co/BAAI/bge-reranker-v2-m3>
- Docker Compose, perfis: <https://docs.docker.com/compose/how-tos/profiles/>
- Docker Compose, mesclagem e `!reset`: <https://docs.docker.com/reference/compose-file/merge/>
