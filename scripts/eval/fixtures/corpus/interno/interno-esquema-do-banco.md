# Esquema do banco do Vértice ERP

Documento interno e fictício do suporte. Descreve as tabelas que o suporte consulta (somente leitura) para investigar chamados. Nunca altere dados direto no banco: correções passam pelas telas ou por um card para o desenvolvimento.

## Clientes

```sql
-- clientes: um registro por cliente (pessoa física ou jurídica)
CREATE TABLE clientes (
    id              bigint PRIMARY KEY,
    razao_social    text NOT NULL,
    documento       text NOT NULL,          -- CPF ou CNPJ, só dígitos
    limite_credito  numeric(14, 2) NOT NULL DEFAULT 0,
    bloqueado       boolean NOT NULL DEFAULT false,
    cliente_desde   date NOT NULL,
    criado_em       timestamptz NOT NULL
);
```

## Pedidos

```sql
-- pedidos.situacao: 'aberto', 'aguardando_credito', 'faturado' ou 'cancelado'
CREATE TABLE pedidos (
    id           bigint PRIMARY KEY,
    cliente_id   bigint NOT NULL REFERENCES clientes (id),
    vendedor_id  bigint NOT NULL,
    situacao     text NOT NULL,
    valor_total  numeric(14, 2) NOT NULL,
    criado_em    timestamptz NOT NULL
);
```

## Títulos a receber

```sql
-- titulos_receber: uma parcela por linha; pago_em nulo = em aberto
CREATE TABLE titulos_receber (
    id          bigint PRIMARY KEY,
    cliente_id  bigint NOT NULL REFERENCES clientes (id),
    pedido_id   bigint REFERENCES pedidos (id),
    valor       numeric(14, 2) NOT NULL,
    vencimento  date NOT NULL,
    pago_em     date
);
```

## Notas fiscais e comissões

```sql
CREATE TABLE notas_fiscais (
    id               bigint PRIMARY KEY,
    pedido_id        bigint NOT NULL REFERENCES pedidos (id),
    chave_acesso     char(44),
    situacao         text NOT NULL,         -- 'pendente', 'autorizada', 'rejeitada', 'cancelada'
    rejeicao_codigo  integer
);

CREATE TABLE comissoes (
    id           bigint PRIMARY KEY,
    vendedor_id  bigint NOT NULL,
    titulo_id    bigint NOT NULL REFERENCES titulos_receber (id),
    percentual   numeric(5, 2) NOT NULL,
    valor        numeric(14, 2) NOT NULL,
    competencia  date NOT NULL              -- primeiro dia do mês de referência
);
```

## Exposição de crédito

A exposição de crédito de um cliente é a soma dos títulos em aberto (`titulos_receber` com `pago_em` nulo) com os pedidos em `aberto` ou `aguardando_credito`. Quando a exposição passa de `clientes.limite_credito`, o pedido novo vai para `aguardando_credito`.
