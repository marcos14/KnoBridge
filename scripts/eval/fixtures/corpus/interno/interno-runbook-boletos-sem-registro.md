# Runbook: boletos parados em "Aguardando registro"

Documento interno e fictício do suporte.

## Sintoma

Boletos emitidos ficam na situação **Aguardando registro** por mais de um dia útil, e a reemissão mostra **Boleto aguardando registro (FIN-030)**.

## Causa mais comum

O registro depende do arquivo de remessa CNAB enviado ao banco. A rotina **remessa-diaria** gera e envia o arquivo todo dia às 06:00. Quando o envio falha (senha do banco trocada, certificado da conexão vencido), os boletos daquele dia ficam sem registro.

## Procedimento

1. Abra **Financeiro > Remessas** e veja a situação da remessa do dia.
2. Se a remessa está **Com erro**, leia a mensagem do banco no detalhe.
3. Corrigido o motivo, clique em **Reenviar remessa**. O banco confirma o registro em até duas horas, pelo arquivo de retorno.
4. Se a remessa está **Enviada** e o retorno não chegou, abra um chamado com o banco informando o número da remessa.
