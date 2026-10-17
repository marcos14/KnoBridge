-- Fictional migration of the Vértice ERP, used only by the KnoBridge evaluation set.
CREATE TABLE titulos_receber (
    id          bigint PRIMARY KEY,
    cliente_id  bigint NOT NULL REFERENCES clientes (id),
    pedido_id   bigint REFERENCES pedidos (id),
    valor       numeric(14, 2) NOT NULL,
    vencimento  date NOT NULL,
    pago_em     date
);

-- Open receivables by customer drive the credit exposure.
CREATE INDEX titulos_receber_abertos_idx ON titulos_receber (cliente_id) WHERE pago_em IS NULL;
