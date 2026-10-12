# Ensaio de chamados por API com dados sintéticos

> 2026-10-12 · Plano [0005](../planos/0005-chamados-por-api.md), subfase F6.2 · executado pelo orquestrador numa stack local (`deploy/docker-compose.yml` + `docker-compose.e2e.yml`, com o receptor de webhook fake), fora da CI

Primeiro uso do recebimento de chamados por API ([ADR 0006](../adr/0006-chamados-por-push.md)) com um volume realista. Os 300 chamados, em pt-BR, saíram do gerador do repositório (`scripts/synthetic_tickets`, semente 7) e descrevem um ERP fictício (Vértice ERP: 24 problemas recorrentes em 6 módulos). Cada chamado tem dados pessoais semeados, listados num gabarito com o marcador esperado. O ensaio mediu o envio, a anonimização, a indexação, as respostas do chat com citação de chamado e o "Abrir chamado" pelo webhook. Nenhum dado real foi usado.

## Configuração

| Item | Valor |
|---|---|
| Stack | compose local com o overlay de E2E (o receptor `webhook-sink`, liberado em `KNOBRIDGE_WEBHOOK_ALLOWED_HOSTS`), banco limpo |
| Provedor | OpenRouter, embedding `openai/text-embedding-3-small`, chat `openai/gpt-6-luna-pro` (temperatura 0,2, similaridade mínima 0,35) |
| Fonte | `tickets`, anonimização ligada, notas internas fora, os quatro status indexados |
| Dados | 300 chamados (abertos, pendentes, resolvidos e fechados; parte com corpo em HTML e com notas internas), 1.612 dados pessoais semeados nos tipos cobertos pelas regras, 130 números de versão que devem ser preservados e 38 nomes de terceiros que nenhuma regra detecta |

## Envio e indexação

| Etapa | Resultado |
|---|---|
| API: 150 chamados em 2 lotes (100 + 50) | 150 `queued`, 4,4 s |
| Reenvio de um chamado igual | `unchanged` (nada reindexado) |
| Upload: 150 chamados em JSONL | 150 `queued`, 0 erros, 2,3 s; `sync: pending`, porque a sincronização do envio da API ainda rodava, e entrou logo depois |
| Indexação dos 300 | 2 execuções `ingest`, cerca de 35 s no total, 954 chunks, 134 mil tokens de embedding, US$ 0,0027 |
| Caixa de entrada no fim | 300 `indexed`, 0 falhas, **nenhum payload bruto guardado** |

## Anonimização

O texto indexado (chunks, título e metadados de citação) de cada chamado foi comparado com o gabarito:

| Tipo | Semeados | Trocados pelo marcador |
|---|---|---|
| Nome do solicitante e dos autores | 267 | 267 |
| Primeiro nome | 608 | 608 |
| Empresa do solicitante | 143 | 143 |
| CNPJ (mensagens públicas / notas internas) | 79 / 48 | 79 / 48 |
| CPF (públicas / internas) | 60 / 53 | 60 / 53 |
| Telefone (públicas / internas) | 72 / 61 | 72 / 61 |
| Cartão (Luhn) | 73 | 73 |
| E-mail | 72 | 72 |
| IP | 76 | 76 |
| **Total** | **1.612** | **1.612 (nenhum vazamento)** |

- **Números de versão** (ex.: `12.6.0.221`, que parecem IP): 130 de 130 preservados.
- **Nomes de terceiros que não estão no payload**: 38 de 38 continuam no texto. É o limite conhecido das regras determinísticas (a spec e o guia avisam: declare-os como autores ou remova-os antes de enviar).
- Ressalva: o gerador e as regras foram escritos no mesmo plano; o ensaio prova que as regras fazem o que a spec promete, não que cobrem tudo que um chamado real traz. O primeiro piloto com dados reais deve repetir a medição com uma amostra revisada à mão.

## Perguntas

Quinze perguntas de suporte, uma por problema, escritas como o usuário escreveria (descrevendo o sintoma, sem o código do erro). Mais uma sem relação. "Acerto" é a resposta citar ao menos um chamado do mesmo problema que esteja resolvido ou fechado.

| | Rodada 1 | Rodada 2 (depois da correção 2) |
|---|---|---|
| Chamado esperado entre as 10 fontes | 13 de 15 | 14 de 15 |
| Resposta que cita chamado esperado | **11 de 15** | **14 de 15** |
| Resposta "não sei" com fontes relevantes recuperadas | 4 | 0 |
| Pergunta sem relação | "sem fonte" sem chamar o LLM, 0,8 s | igual |
| Latência mediana | 5,6 s | 6,5 s |
| Tokens de chat (16 perguntas) | 121 mil / 5 mil | 133 mil / 5,5 mil |

Conferi três respostas da rodada 2 contra a solução do artigo do problema (turno anterior aberto, saldo negativo, boleto não registrado), e as três batiam com o caminho do menu e os passos certos. A pergunta que ficou sem acerto ("As vendas no débito e no crédito não passam no caixa, como volto a receber?") não recuperou nenhum chamado do problema (TEF sem comunicação): a paráfrase não compartilha termos com os chamados. Esse caso fica para a comparação de embeddings ([F6.3](../planos/0005-chamados-por-api.md)).

## Abrir chamado

Na resposta sem fonte (a pergunta sem relação):
- a prévia trouxe resumo gerado pelo modelo (176 caracteres), nome e e-mail do solicitante;
- a criação respondeu 202;
- a entrega foi aceita pelo receptor na primeira tentativa, em 3 s, com a assinatura `KnoBridge-Signature` conferida, e o chat recebeu o número `KB-0001`.

O evento de teste (`ticket.test`) também foi verificado pelo receptor.

## Achados e correções

Cada correção entrou com teste na mesma subfase.

1. **Sincronização pendente com o gatilho errado**: o upload chegou enquanto a sincronização do envio pela API rodava. A execução seguinte, criada pela sincronização pendente, ficou com o gatilho `harness`, que estava fixo desde o plano 0004, quando só o harness pedia sincronização pendente. Agora o gatilho vem do tipo da fonte: `ingest` para `tickets` e `harness` para `runner`. Na rodada 2, as duas execuções aparecem como `ingest`.
2. **Solução separada do problema no chunking**: na rodada 1, quatro respostas disseram "não sei" mesmo com chamados do problema entre as fontes. A pergunta descreve o sintoma e recupera o trecho do **problema**; a solução ficava num trecho próprio, raramente recuperado. Numa delas, as 10 fontes eram trechos de problema. Agora a seção `## Solução` vai no primeiro trecho, junto do título, dos metadados e do problema, quando os quatro cabem em `MAX_TOKENS`, e só fica separada quando não cabem ([chamados.md, Chunking](../specs/chamados.md#chunking)). Resultado: de 11 para 14 acertos em 15, e de 1.139 para 954 trechos. Fontes que já indexaram chamados só passam a usar o novo corte quando os chamados forem reenviados com `updated_at` mais novo (o hash do documento não muda com o chunking).

## Custo

Gasto do ensaio na chave do OpenRouter (duas indexações completas, as duas rodadas de perguntas, as prévias de "Abrir chamado" e a conferência dos embeddings do Gemini da F5.1): **US$ 0,03**.

## Como repetir

```bash
cd scripts && uv run python -m synthetic_tickets --seed 7 --tickets 300 --out ../../kb-sinteticos
docker compose -p knobridge-chamados -f deploy/docker-compose.yml -f deploy/docker-compose.e2e.yml up -d --build --wait
# painel: Provedores (OpenRouter) → Coleções → Fontes > Nova fonte (Chamados) → Integração (token)
# envie metade pela API e o resto pela aba Upload; ligue a coleção e o webhook (http://webhook-sink:8090/hook) ao assistente
```

Passo a passo em [docs/guias/receber-chamados-por-api.md](../guias/receber-chamados-por-api.md).
