# Runbook: rejeição 539 na NF-e

Documento interno e fictício do suporte.

## Sintoma

O cliente transmite a nota e recebe **Rejeição 539 – Duplicidade de NF-e com diferença na chave de acesso**. Em geral, a primeira transmissão chegou à SEFAZ, mas a resposta se perdeu por queda de conexão, e o sistema transmitiu de novo com outra data de emissão.

## Procedimento

1. Peça a chave de acesso da nota e consulte a situação no portal da SEFAZ do estado.
2. Se a nota consta **autorizada** na SEFAZ, use **Fiscal > Notas fiscais > Ações > Sincronizar autorização**. O Vértice ERP baixa o protocolo e a nota passa para **Autorizada** com a chave original.
3. Se a nota não consta na SEFAZ, aguarde 10 minutos e transmita de novo pela própria nota (nunca crie uma nota nova para o mesmo pedido).
4. Se a ação **Sincronizar autorização** não aparece, a versão do cliente é anterior à 12.3: oriente a atualização.

## Não fazer

- Não inutilize o número da nota enquanto a situação na SEFAZ não estiver clara.
- Não altere `notas_fiscais.situacao` no banco.
