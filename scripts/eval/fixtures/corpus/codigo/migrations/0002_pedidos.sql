-- Fictional migration of the Vértice ERP, used only by the KnoBridge evaluation set.
CREATE TABLE pedidos (
    id           bigint PRIMARY KEY,
    cliente_id   bigint NOT NULL REFERENCES clientes (id),
    vendedor_id  bigint NOT NULL,
    situacao     text NOT NULL CHECK (situacao IN ('aberto', 'aguardando_credito', 'faturado', 'cancelado')),
    valor_total  numeric(14, 2) NOT NULL,
    criado_em    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX pedidos_cliente_situacao_idx ON pedidos (cliente_id, situacao);
