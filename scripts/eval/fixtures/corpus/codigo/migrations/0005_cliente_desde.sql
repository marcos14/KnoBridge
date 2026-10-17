-- Fictional migration of the Vértice ERP, used only by the KnoBridge evaluation set.
-- Version 12.4: the start of the relationship drives the 5% tolerance for older customers.
ALTER TABLE clientes ADD COLUMN cliente_desde date;
UPDATE clientes SET cliente_desde = criado_em::date WHERE cliente_desde IS NULL;
ALTER TABLE clientes ALTER COLUMN cliente_desde SET NOT NULL;
