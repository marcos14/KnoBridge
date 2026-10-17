# Emissão de NF-e

Conteúdo fictício do manual do usuário do **Vértice ERP**.

## Passo a passo

1. Abra **Fiscal > Notas fiscais > Emitir**.
2. Escolha o pedido faturado e confira destinatário, produtos e impostos.
3. Clique em **Transmitir**. A situação passa para **Autorizada** quando a SEFAZ aceita a nota.

## Mensagens de erro

- **Rejeição 539 – Duplicidade de NF-e com diferença na chave de acesso**: a SEFAZ já recebeu uma nota com esse número. Não emita outra nota com o mesmo pedido. Aguarde alguns minutos e use **Consultar situação** na nota; se continuar, abra um chamado.
- **Rejeição 204 – Duplicidade de NF-e**: a nota já foi autorizada antes. Use **Consultar situação** para trazer a autorização.
- **Certificado digital vencido (FIS-002)**: o certificado A1 da empresa venceu. Peça ao responsável para instalar o novo certificado em **Configurações > Fiscal > Certificado**.

## Cancelamento

Uma nota autorizada pode ser cancelada em até 24 horas em **Fiscal > Notas fiscais > Cancelar**, com uma justificativa de pelo menos 15 caracteres.
