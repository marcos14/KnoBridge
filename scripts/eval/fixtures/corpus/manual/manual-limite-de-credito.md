# Limite de crédito do cliente

Conteúdo fictício do manual do usuário do **Vértice ERP**.

## Como funciona

Cada cliente tem um limite de crédito, que é o valor máximo que ele pode dever para a empresa ao mesmo tempo. Ao salvar um pedido, o sistema soma o que o cliente ainda deve (boletos em aberto) e os pedidos dele que ainda não foram faturados. Se essa soma passar do limite, o pedido não é recusado: ele fica com a situação **Aguardando liberação de crédito**.

## Quem libera

Só quem tem o perfil **Gerente financeiro** libera pedidos, na tela **Vendas > Liberação de crédito**. O gerente pode liberar só aquele pedido ou aumentar o limite do cliente.

## Cliente novo

Cliente recém-cadastrado começa com limite zero: as compras a prazo dependem da análise de crédito feita pelo financeiro. Até a análise, ele pode comprar à vista (dinheiro, PIX ou cartão).

## Dúvidas comuns

- **O pedido some depois de liberado?** Não. Ele volta para a situação **Aberto** e segue o fluxo normal de faturamento.
- **O limite muda sozinho?** Não. Só o financeiro altera o limite, no cadastro do cliente, aba **Crédito**.
