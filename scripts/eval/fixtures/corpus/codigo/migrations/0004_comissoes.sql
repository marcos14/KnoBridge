-- Fictional migration of the Vértice ERP, used only by the KnoBridge evaluation set.
CREATE TABLE comissoes (
    id           bigint PRIMARY KEY,
    vendedor_id  bigint NOT NULL,
    titulo_id    bigint NOT NULL REFERENCES titulos_receber (id),
    percentual   numeric(5, 2) NOT NULL,
    valor        numeric(14, 2) NOT NULL,
    competencia  date NOT NULL
);

CREATE UNIQUE INDEX comissoes_titulo_competencia_key ON comissoes (titulo_id, competencia);
