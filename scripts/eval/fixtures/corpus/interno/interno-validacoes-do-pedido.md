# Validações do pedido de venda

Documento interno e fictício do suporte. Lista as validações que o Vértice ERP faz ao salvar um pedido, com o código que aparece no log do pedido (aba **Histórico**, visível só para o suporte).

| Código | Regra | Efeito |
|---|---|---|
| VAL-PED-010 | Cliente com `bloqueado = true` no cadastro. | Pedido recusado. |
| VAL-PED-014 | Cliente com algum título vencido há mais de 30 dias e não pago. | Pedido vai para **Aguardando liberação de crédito**, mesmo dentro do limite. |
| VAL-PED-020 | Exposição de crédito acima do limite. | Pedido vai para **Aguardando liberação de crédito**. |
| VAL-PED-031 | Produto sem estoque no depósito escolhido. | Aviso; o pedido é salvo. |

## Tolerância para clientes antigos

Desde a versão 12.4, clientes com mais de 2 anos de relacionamento (`cliente_desde`) têm uma tolerância de 5% acima do limite antes da VAL-PED-020 travar o pedido. Por isso um cliente antigo pode passar um pouco do limite sem o pedido parar. A VAL-PED-014 não tem tolerância.

## Como investigar

1. Abra o pedido e veja a aba **Histórico**: a validação que travou aparece com o código.
2. Para a VAL-PED-014, consulte os títulos vencidos do cliente em **Financeiro > Contas a receber**.
3. Oriente o cliente a falar com o gerente financeiro; o suporte não libera crédito.
