"""Back-office problems of the fictitious Vértice ERP: finance, payroll, sales."""

from __future__ import annotations

from synthetic_tickets.problem import Problem

FINANCEIRO = "Financeiro"
FOLHA = "Folha de Pagamento"
VENDAS = "Vendas e Pedidos"

GESTAO: tuple[Problem, ...] = (
    Problem(
        slug="financeiro-boleto-nao-registrado",
        product=FINANCEIRO,
        category="Financeiro",
        tags=("boleto", "cobrança", "cnab"),
        titles=("Boleto não registrado no banco", "Cliente não consegue pagar o boleto"),
        complaints=(
            "Os clientes dizem que o boleto não é encontrado no banco na hora de pagar.",
            "Emitimos os boletos da semana e o banco diz que não estão registrados.",
        ),
        symptom="O banco não encontra os boletos emitidos.",
        cause="O arquivo de remessa CNAB não foi gerado nem enviado ao banco.",
        steps=(
            "Acesse Financeiro > Cobrança > Gerar remessa.",
            "Envie o arquivo gerado pelo internet banking.",
            "No dia seguinte, importe o arquivo de retorno do banco.",
        ),
        solution=(
            "A remessa CNAB não tinha sido enviada. Gerada em Financeiro > Cobrança > Gerar "
            "remessa e enviada ao banco, os boletos foram registrados."
        ),
        questions=(
            "O pagador diz que o código de barras não existe no banco, o que faltou?",
            "Como envio a remessa de cobrança para o banco registrar os títulos?",
        ),
    ),
    Problem(
        slug="financeiro-conciliacao-ofx",
        product=FINANCEIRO,
        category="Financeiro",
        tags=("conciliação", "ofx", "banco"),
        titles=("Conciliação bancária não importa o OFX", "Extrato OFX recusado na conciliação"),
        complaints=(
            "Tento importar o extrato OFX na conciliação e aparece 'conta não encontrada'.",
            "O arquivo OFX do banco não entra na conciliação bancária.",
        ),
        symptom="A importação do extrato OFX falha com 'conta não encontrada'.",
        cause="Agência e conta do arquivo OFX não batem com o cadastro da conta no sistema.",
        steps=(
            "Abra o OFX e confira agência e conta.",
            "Ajuste agência e conta em Financeiro > Contas bancárias.",
            "Importe o extrato de novo.",
        ),
        solution=(
            "O cadastro da conta tinha o dígito da agência diferente do extrato. Ajustado em "
            "Financeiro > Contas bancárias, o OFX importou."
        ),
        questions=(
            "O extrato do banco é recusado com a mensagem de conta inexistente.",
            "Por que a importação do arquivo do banco não reconhece minha conta?",
        ),
    ),
    Problem(
        slug="financeiro-juros-atraso",
        product=FINANCEIRO,
        category="Financeiro",
        tags=("juros", "multa", "recebimento"),
        titles=("Juros não calculados no recebimento em atraso", "Multa por atraso zerada"),
        complaints=(
            "Recebemos um título vencido e o sistema não calculou juros nem multa.",
            "Os boletos pagos em atraso entram sem multa e sem juros.",
        ),
        symptom="Recebimentos em atraso entram sem multa e sem juros.",
        cause="A carteira de cobrança está sem percentual de multa e de juros ao dia.",
        steps=(
            "Acesse Financeiro > Cobrança > Carteiras.",
            "Informe o percentual de multa e o de juros ao dia.",
            "Os títulos emitidos depois disso já saem com os encargos.",
        ),
        solution=(
            "A carteira estava sem multa e juros configurados. Depois do ajuste em "
            "Financeiro > Cobrança > Carteiras, os encargos passaram a ser calculados."
        ),
        questions=(
            "Onde configuro os encargos cobrados de quem paga depois do vencimento?",
            "O título quitado com atraso não teve acréscimo, o que está errado?",
        ),
    ),
    Problem(
        slug="financeiro-baixa-duplicada",
        product=FINANCEIRO,
        category="Financeiro",
        tags=("baixa", "contas a receber"),
        titles=("Título baixado duas vezes", "Baixa duplicada no contas a receber"),
        complaints=(
            "Um título apareceu baixado duas vezes e o caixa ficou com valor a mais.",
            "Importamos o retorno do banco duas vezes e os títulos ficaram com baixa duplicada.",
        ),
        symptom="O mesmo título tem duas baixas e o saldo fica errado.",
        cause="O arquivo de retorno do banco foi importado duas vezes.",
        steps=(
            "Acesse Financeiro > Contas a receber e abra o título.",
            "Use Estornar baixa na baixa repetida.",
            "Confira o saldo da conta.",
        ),
        solution=(
            "A baixa repetida foi estornada em Financeiro > Contas a receber > Estornar baixa e "
            "o saldo voltou ao correto."
        ),
        questions=(
            "Como desfaço um recebimento que entrou em dobro?",
            "O retorno do banco foi processado duas vezes, como corrigir os títulos?",
        ),
    ),
    Problem(
        slug="folha-esocial-s1200",
        product=FOLHA,
        category="RH",
        tags=("esocial", "folha"),
        titles=("Evento S-1200 do eSocial rejeitado", "eSocial recusa a remuneração do mês"),
        complaints=(
            "O evento S-1200 voltou rejeitado do eSocial para vários funcionários.",
            "Não consigo fechar a folha porque o S-1200 é recusado.",
        ),
        symptom="O eSocial rejeita o evento S-1200 de remuneração.",
        cause="Uma rubrica nova foi criada sem a natureza e as incidências do eSocial.",
        steps=(
            "Acesse Folha > Rubricas e abra a rubrica indicada na rejeição.",
            "Preencha a natureza da rubrica e as incidências.",
            "Reenvie o evento S-1200.",
        ),
        solution=(
            "A rubrica nova estava sem natureza e incidências. Ajustada em Folha > Rubricas, o "
            "S-1200 foi aceito no reenvio."
        ),
        questions=(
            "O evento de remuneração mensal foi devolvido pelo governo, como corrijo?",
            "O que preencher numa rubrica nova para o eSocial aceitar?",
        ),
    ),
    Problem(
        slug="folha-ferias-sem-medias",
        product=FOLHA,
        category="RH",
        tags=("férias", "médias", "folha"),
        titles=("Férias calculadas com valor errado", "Médias de horas extras fora das férias"),
        complaints=(
            "O recibo de férias saiu sem as médias de horas extras do funcionário.",
            "O valor das férias ficou menor do que o esperado.",
        ),
        symptom="O cálculo de férias não inclui as médias de horas extras.",
        cause="A rubrica de horas extras não está marcada para compor médias.",
        steps=(
            "Acesse Folha > Rubricas e abra a rubrica de horas extras.",
            "Marque 'compõe médias de férias e 13º'.",
            "Recalcule as férias.",
        ),
        solution=(
            "A rubrica de horas extras não compunha médias. Marcada em Folha > Rubricas, o "
            "recálculo das férias trouxe os valores corretos."
        ),
        questions=(
            "O pagamento do descanso anual veio sem o adicional das horas trabalhadas a mais.",
            "Como faço uma rubrica entrar na média do 13º e das férias?",
        ),
    ),
    Problem(
        slug="folha-importacao-ponto-afd",
        product=FOLHA,
        category="RH",
        tags=("ponto", "importação"),
        titles=("Importação do ponto eletrônico falha", "Arquivo do relógio de ponto não importa"),
        complaints=(
            "O arquivo do relógio de ponto não importa, diz layout inválido.",
            "Trocamos o relógio de ponto e a importação das marcações parou.",
        ),
        symptom="A importação das marcações do ponto falha com 'layout inválido'.",
        cause="O relógio novo gera o arquivo no layout AFD da Portaria 671.",
        steps=(
            "Acesse Folha > Ponto > Importar marcações.",
            "Selecione o layout AFD (Portaria 671).",
            "Importe o arquivo de novo.",
        ),
        solution=(
            "O relógio novo gera AFD da Portaria 671. Com esse layout selecionado em "
            "Folha > Ponto > Importar marcações, o arquivo importou."
        ),
        questions=(
            "O arquivo de marcações do novo equipamento de ponto é recusado.",
            "Qual layout escolher para importar o AFD da Portaria 671?",
        ),
    ),
    Problem(
        slug="folha-adiantamento-13",
        product=FOLHA,
        category="RH",
        tags=("13º", "folha"),
        titles=("Adiantamento do 13º não aparece na folha", "Primeira parcela do 13º sumiu"),
        complaints=(
            "A primeira parcela do 13º não apareceu na folha de novembro.",
            "Fechamos a folha e o adiantamento do décimo terceiro ficou de fora.",
        ),
        symptom="A primeira parcela do 13º não aparece na folha.",
        cause="O adiantamento precisa ser gerado antes do fechamento da folha do mês.",
        steps=(
            "Reabra a folha do mês, se já estiver fechada.",
            "Acesse Folha > 13º salário > 1ª parcela e gere o adiantamento.",
            "Feche a folha de novo.",
        ),
        solution=(
            "O adiantamento foi gerado em Folha > 13º salário > 1ª parcela antes de fechar a "
            "folha e passou a constar."
        ),
        questions=(
            "A gratificação natalina antecipada não saiu no holerite, como incluo?",
            "Em que ordem gero a primeira parcela do 13º e fecho a folha?",
        ),
    ),
    Problem(
        slug="vendas-pedido-bloqueado-credito",
        product=VENDAS,
        category="Comercial",
        tags=("pedido", "crédito"),
        titles=("Pedido bloqueado por limite de crédito", "Pedido não libera para faturar"),
        complaints=(
            "O pedido do cliente ficou bloqueado por limite de crédito e não fatura.",
            "Não consigo faturar o pedido, aparece bloqueio de crédito.",
        ),
        symptom="O pedido fica bloqueado por limite de crédito e não pode ser faturado.",
        cause="O valor em aberto do cliente passou do limite de crédito cadastrado.",
        steps=(
            "Peça a um gerente para liberar o pedido em Vendas > Pedidos bloqueados.",
            "Para evitar novos bloqueios, revise o limite de crédito no cadastro do cliente.",
        ),
        solution=(
            "O gerente liberou o pedido em Vendas > Pedidos bloqueados. Para os próximos, o "
            "limite de crédito do cliente foi revisto."
        ),
        questions=(
            "Quem pode liberar uma venda barrada pelo limite do cliente?",
            "O faturamento está travado por crédito, como prossigo?",
        ),
    ),
    Problem(
        slug="vendas-tabela-preco-vigencia",
        product=VENDAS,
        category="Comercial",
        tags=("preço", "tabela"),
        titles=("Preço errado no pedido", "Tabela de preço nova não aplicada"),
        complaints=(
            "Os pedidos de hoje saíram com o preço antigo, a tabela nova não foi aplicada.",
            "O vendedor lança o pedido e o preço vem diferente da tabela.",
        ),
        symptom="Os pedidos usam o preço antigo em vez da tabela nova.",
        cause="A tabela nova tem data de vigência futura ou não está vinculada ao cliente.",
        steps=(
            "Acesse Vendas > Tabelas de preço e confira a data de vigência.",
            "Confira a tabela vinculada no cadastro do cliente.",
            "Atualize o preço dos pedidos em aberto.",
        ),
        solution=(
            "A tabela nova começava só no mês seguinte. Corrigida a vigência em Vendas > Tabelas "
            "de preço, os pedidos passaram a usar o preço novo."
        ),
        questions=(
            "O reajuste de preços não está valendo nas vendas, o que conferir?",
            "Como vinculo uma lista de preços a um cliente?",
        ),
    ),
    Problem(
        slug="vendas-comissao-zerada",
        product=VENDAS,
        category="Comercial",
        tags=("comissão", "vendedor"),
        titles=("Comissão do vendedor zerada no relatório", "Relatório de comissões sem valores"),
        complaints=(
            "O relatório de comissões saiu zerado para um vendedor novo.",
            "A comissão do mês de um representante não foi calculada.",
        ),
        symptom="O relatório de comissões mostra zero para um vendedor.",
        cause="O vendedor foi cadastrado sem percentual de comissão.",
        steps=(
            "Acesse Vendas > Vendedores e informe o percentual de comissão.",
            "Use Vendas > Comissões > Reprocessar para o período.",
        ),
        solution=(
            "O vendedor estava sem percentual. Cadastrado o percentual e reprocessadas as "
            "comissões do período, o relatório saiu correto."
        ),
        questions=(
            "O representante contratado este mês não tem nada a receber no relatório.",
            "Como recalculo as comissões de um período que já passou?",
        ),
    ),
    Problem(
        slug="vendas-orcamento-v118",
        product=VENDAS,
        category="Comercial",
        tags=("orçamento", "pedido"),
        titles=("Erro V-118 ao converter orçamento em pedido", "Orçamento não vira pedido"),
        complaints=(
            "Ao converter o orçamento em pedido aparece o erro V-118.",
            "O cliente aprovou o orçamento mas não consigo transformar em pedido.",
        ),
        symptom="A conversão do orçamento em pedido falha com o erro V-118.",
        cause="O orçamento passou da data de validade.",
        steps=(
            "Abra o orçamento em Vendas > Orçamentos.",
            "Use Renovar validade e confira os preços.",
            "Converta em pedido.",
        ),
        solution=(
            "O orçamento estava vencido. Renovada a validade em Vendas > Orçamentos, a conversão "
            "em pedido funcionou."
        ),
        questions=(
            "A proposta aprovada pelo cliente não pode ser transformada em venda.",
            "O que fazer com um orçamento que passou da validade?",
        ),
    ),
)
