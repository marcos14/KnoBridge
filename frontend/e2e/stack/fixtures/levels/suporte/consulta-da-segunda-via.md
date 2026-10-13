# Consulta da segunda via

Material sintético para o E2E da stack.

## Conferir quem pediu emitir a segunda via do boleto

Para conferir quem pediu emitir a segunda via do boleto de uma fatura, rode a consulta somente
de leitura abaixo e compare a data do pedido com a do vencimento.

```sql
SELECT pedido_em, usuario FROM segundas_vias WHERE fatura = :fatura ORDER BY pedido_em;
```
