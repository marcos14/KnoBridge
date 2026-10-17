-- Fictional migration of the Vértice ERP, used only by the KnoBridge evaluation set.
CREATE TABLE clientes (
    id              bigint PRIMARY KEY,
    razao_social    text NOT NULL,
    documento       text NOT NULL,
    limite_credito  numeric(14, 2) NOT NULL DEFAULT 0,
    bloqueado       boolean NOT NULL DEFAULT false,
    criado_em       timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX clientes_documento_key ON clientes (documento);
