# Segunda via de boleto

Conteúdo fictício do manual do usuário do **Vértice ERP**.

## Onde fica

Menu **Financeiro > Contas a receber > Títulos**. Procure o título pelo número, pelo cliente ou pelo vencimento.

## Passo a passo

1. Selecione o título na lista.
2. Clique em **Reemitir boleto**.
3. Confira a nova data de vencimento e clique em **Gerar PDF**.
4. Use **Enviar por e-mail** para mandar o boleto ao cliente.

## Boleto vencido

Quando o título já venceu, o Vértice ERP recalcula o valor na reemissão: multa de 2% sobre o valor original e juros de 0,033% por dia de atraso. A nova data de vencimento pode ser escolhida, mas não pode passar de 30 dias a partir de hoje.

## Mensagens de erro

- **Título já liquidado (FIN-021)**: o título foi pago e baixado. Não há segunda via; consulte o recibo em **Financeiro > Recebimentos**.
- **Boleto aguardando registro (FIN-030)**: o banco ainda não confirmou o registro. Aguarde até o dia útil seguinte e tente de novo.
