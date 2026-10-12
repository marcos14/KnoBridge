"""Store-floor problems of the fictitious Vértice ERP: cash register, fiscal documents, stock."""

from __future__ import annotations

from synthetic_tickets.problem import Problem

CAIXA = "Caixa (PDV)"
FISCAL = "Fiscal (NF-e e NFC-e)"
ESTOQUE = "Estoque"

LOJA: tuple[Problem, ...] = (
    Problem(
        slug="caixa-erro-4021-fechamento",
        product=CAIXA,
        category="Operação de loja",
        tags=("caixa", "fechamento", "sangria"),
        titles=("Erro 4021 ao fechar o caixa", "Caixa não fecha: erro 4021"),
        complaints=(
            "Ao fechar o caixa no fim do dia aparece o erro 4021 e o sistema não deixa concluir.",
            "Desde ontem o fechamento do caixa trava com a mensagem de erro 4021.",
        ),
        symptom="O fechamento do caixa é recusado com o erro 4021.",
        cause="O turno anterior ficou com uma sangria iniciada e não finalizada.",
        steps=(
            "Acesse Caixa > Movimentos > Sangrias.",
            "Finalize a sangria pendente do turno anterior.",
            "Tente fechar o caixa de novo.",
        ),
        solution=(
            "O erro 4021 indica sangria pendente. Finalizar a sangria do turno anterior em "
            "Caixa > Movimentos > Sangrias libera o fechamento."
        ),
        questions=(
            "O que fazer quando o fechamento do caixa é bloqueado no fim do expediente?",
            "Por que o PDV pede para resolver a retirada de dinheiro antes de encerrar o dia?",
        ),
    ),
    Problem(
        slug="caixa-tef-sem-comunicacao",
        product=CAIXA,
        category="Operação de loja",
        tags=("caixa", "tef", "cartão"),
        titles=("Pagamento com cartão não conclui no TEF", "TEF sem comunicação no caixa"),
        complaints=(
            "Quando passo o cartão o caixa fica em 'aguardando TEF' e depois mostra TEF-12.",
            "Nenhum pagamento com cartão passa hoje, aparece TEF sem comunicação.",
        ),
        symptom="Vendas no cartão param em 'aguardando TEF' e terminam com o erro TEF-12.",
        cause="O serviço do gerenciador TEF parou no computador do caixa.",
        steps=(
            "No computador do caixa, abra os serviços do Windows.",
            "Reinicie o serviço GerenciadorTEF.",
            "Em Configurações > Periféricos > TEF, confira se a porta do terminal é 4096.",
        ),
        solution=(
            "Reiniciar o serviço GerenciadorTEF no computador do caixa e conferir a porta 4096 "
            "no cadastro do terminal resolveu a comunicação."
        ),
        questions=(
            "As vendas no débito e no crédito não passam no caixa, como volto a receber?",
            "O que significa a mensagem TEF-12 no PDV?",
        ),
    ),
    Problem(
        slug="caixa-cupom-nao-imprime",
        product=CAIXA,
        category="Operação de loja",
        tags=("caixa", "impressora", "cupom"),
        titles=("Cupom não sai na impressora", "Impressora do caixa parou de imprimir o cupom"),
        complaints=(
            "A venda é concluída mas o cupom não sai na impressora térmica.",
            "Trocamos a impressora do caixa e agora nada é impresso.",
        ),
        symptom="A venda é concluída, mas o cupom não é impresso.",
        cause="O modelo ou a porta da impressora térmica estão errados no cadastro do periférico.",
        steps=(
            "Acesse Configurações > Periféricos > Impressora.",
            "Selecione o modelo da impressora térmica instalada e a porta USB virtual.",
            "Use o botão Testar impressão antes de voltar a vender.",
        ),
        solution=(
            "A impressora estava cadastrada com outro modelo. Ajustar o modelo e a porta USB "
            "virtual em Configurações > Periféricos fez o cupom voltar a sair."
        ),
        questions=(
            "Troquei a impressora térmica e o comprovante da venda não aparece, o que configurar?",
            "Como faço o teste de impressão do PDV?",
        ),
    ),
    Problem(
        slug="caixa-turno-anterior-aberto",
        product=CAIXA,
        category="Operação de loja",
        tags=("caixa", "turno", "abertura"),
        titles=("Não consigo abrir o caixa: turno anterior aberto", "Abertura do caixa bloqueada"),
        complaints=(
            "De manhã o caixa não abre, diz que existe um turno anterior em aberto.",
            "A operadora não consegue iniciar o dia porque o turno de ontem ficou aberto.",
        ),
        symptom="A abertura do caixa é recusada porque há um turno anterior em aberto.",
        cause="O turno do dia anterior não foi encerrado (queda de energia ou saída sem fechar).",
        steps=(
            "Peça a um supervisor para acessar Caixa > Turnos.",
            "Encerre o turno pendente com a senha de gerente.",
            "Abra o novo turno normalmente.",
        ),
        solution=(
            "O supervisor encerrou o turno pendente em Caixa > Turnos com a senha de gerente e "
            "o caixa abriu."
        ),
        questions=(
            "O PDV não deixa começar o expediente porque o dia anterior não foi encerrado.",
            "Quem pode encerrar um turno que ficou aberto depois de uma queda de energia?",
        ),
    ),
    Problem(
        slug="fiscal-rejeicao-539-duplicidade",
        product=FISCAL,
        category="Fiscal",
        tags=("nfe", "rejeição", "sefaz"),
        titles=("NF-e rejeitada com código 539", "Rejeição 539: duplicidade de NF-e"),
        complaints=(
            "Tentei transmitir a nota e voltou rejeição 539, duplicidade de NF-e.",
            "A nota fiscal caiu por timeout e no reenvio a SEFAZ devolveu a rejeição 539.",
        ),
        symptom="O reenvio da NF-e volta com a rejeição 539 (duplicidade).",
        cause="A primeira transmissão foi autorizada, mas o retorno não chegou ao sistema.",
        steps=(
            "Acesse Fiscal > Consultar protocolo e consulte a nota pela chave.",
            "Se a SEFAZ mostrar a nota autorizada, use Vincular protocolo.",
            "Não reenvie a nota com o mesmo número.",
        ),
        solution=(
            "A nota já estava autorizada. Consultar o protocolo em Fiscal > Consultar protocolo "
            "e vincular a autorização resolveu, sem reenviar."
        ),
        questions=(
            "A SEFAZ diz que a nota já existe quando eu reenvio, o que fazer?",
            "Como recuperar a autorização de uma nota que caiu por tempo esgotado?",
        ),
    ),
    Problem(
        slug="fiscal-certificado-vencido",
        product=FISCAL,
        category="Fiscal",
        tags=("nfe", "certificado"),
        titles=("Erro de certificado digital ao transmitir NF-e", "Certificado digital vencido"),
        complaints=(
            "Nenhuma nota é transmitida, aparece erro 280 de certificado digital.",
            "Hoje cedo as notas começaram a falhar com mensagem de certificado inválido.",
        ),
        symptom="Toda transmissão falha com o erro 280 de certificado digital.",
        cause="O certificado A1 da empresa venceu.",
        steps=(
            "Renove o certificado A1 com a certificadora.",
            "Importe o novo arquivo em Fiscal > Certificados.",
            "Reinicie o serviço de transmissão.",
        ),
        solution=(
            "O certificado A1 estava vencido. Importar o certificado renovado em "
            "Fiscal > Certificados e reiniciar o serviço de transmissão resolveu."
        ),
        questions=(
            "Onde troco o certificado A1 quando ele expira?",
            "O que é o erro 280 na emissão de nota fiscal?",
        ),
    ),
    Problem(
        slug="fiscal-sped-registro-c170",
        product=FISCAL,
        category="Fiscal",
        tags=("sped", "obrigações"),
        titles=("SPED Fiscal com erro no registro C170", "Validador do SPED acusa erro no C170"),
        complaints=(
            "O validador do SPED Fiscal acusa erro no registro C170 em vários itens.",
            "Não consigo entregar o SPED do mês, o PVA reclama do C170.",
        ),
        symptom="O PVA do SPED Fiscal aponta erros no registro C170.",
        cause="Há produtos sem NCM no cadastro, e o registro sai incompleto.",
        steps=(
            "Gere o relatório Fiscal > SPED > Inconsistências.",
            "Preencha o NCM dos produtos listados.",
            "Gere o arquivo do SPED de novo e valide no PVA.",
        ),
        solution=(
            "Os produtos listados no relatório de inconsistências estavam sem NCM. Depois do "
            "cadastro, o arquivo do SPED foi gerado de novo e validou."
        ),
        questions=(
            "O programa validador recusa o arquivo da escrituração fiscal por causa dos itens.",
            "Como descubro quais produtos estão sem NCM antes de gerar o SPED?",
        ),
    ),
    Problem(
        slug="fiscal-nfce-contingencia",
        product=FISCAL,
        category="Fiscal",
        tags=("nfce", "contingência"),
        titles=("NFC-e presa em contingência", "Cupons fiscais não saem da contingência"),
        complaints=(
            "A internet caiu ontem e as NFC-e ficaram em contingência até agora.",
            "Tenho dezenas de cupons em contingência que não foram transmitidos.",
        ),
        symptom="NFC-e emitidas sem internet continuam em contingência depois que a rede volta.",
        cause="A transmissão das notas em contingência é manual nesta versão.",
        steps=(
            "Com a internet funcionando, acesse Fiscal > Contingência.",
            "Use Transmitir pendentes.",
            "Confira se nenhuma nota passou do prazo de 24 horas.",
        ),
        solution=(
            "As notas foram transmitidas por Fiscal > Contingência > Transmitir pendentes, "
            "dentro do prazo de 24 horas."
        ),
        questions=(
            "A rede voltou mas os cupons emitidos offline continuam pendentes, como envio?",
            "Qual é o prazo para transmitir as notas emitidas sem internet?",
        ),
    ),
    Problem(
        slug="estoque-saldo-negativo",
        product=ESTOQUE,
        category="Estoque",
        tags=("estoque", "saldo"),
        titles=("Estoque negativo após a venda", "Produto com saldo negativo"),
        complaints=(
            "Vários produtos estão com estoque negativo depois das vendas do fim de semana.",
            "O relatório de posição mostra saldo negativo em itens que não deveriam.",
        ),
        symptom="Produtos ficam com saldo negativo depois de vendas.",
        cause="O parâmetro 'permitir venda sem saldo' está ligado.",
        steps=(
            "Acesse Estoque > Parâmetros.",
            "Desligue 'permitir venda sem saldo'.",
            "Faça um ajuste de inventário dos itens negativos.",
        ),
        solution=(
            "O parâmetro de venda sem saldo estava ligado. Desligado em Estoque > Parâmetros e "
            "feito o ajuste de inventário, os saldos voltaram ao normal."
        ),
        questions=(
            "Como impedir que o sistema venda item que não tem quantidade disponível?",
            "Por que aparecem quantidades abaixo de zero na posição de estoque?",
        ),
    ),
    Problem(
        slug="estoque-inventario-nao-finaliza",
        product=ESTOQUE,
        category="Estoque",
        tags=("estoque", "inventário"),
        titles=("Inventário não finaliza", "Inventário parado: itens sem contagem"),
        complaints=(
            "Terminamos a contagem mas o inventário não finaliza, diz que há itens sem contagem.",
            "O botão de finalizar o inventário mostra um aviso de itens pendentes.",
        ),
        symptom="O inventário não pode ser finalizado por haver itens sem contagem.",
        cause="Itens do escopo do inventário não receberam quantidade contada.",
        steps=(
            "Acesse Estoque > Inventário > Itens pendentes.",
            "Informe a contagem ou zere os itens que não existem na loja.",
            "Finalize o inventário.",
        ),
        solution=(
            "Os itens pendentes foram contados ou zerados em Estoque > Inventário > Itens "
            "pendentes e o inventário finalizou."
        ),
        questions=(
            "A contagem física acabou mas o sistema não deixa concluir o balanço.",
            "Onde vejo quais itens ficaram de fora da contagem?",
        ),
    ),
    Problem(
        slug="estoque-transferencia-filial",
        product=ESTOQUE,
        category="Estoque",
        tags=("estoque", "transferência", "filial"),
        titles=(
            "Transferência entre filiais não aparece no destino",
            "Mercadoria transferida não entrou na outra loja",
        ),
        complaints=(
            "Fizemos a transferência para a filial e o estoque da loja de destino não mudou.",
            "A nota de transferência foi emitida mas a outra loja não vê a mercadoria.",
        ),
        symptom="A mercadoria transferida não aparece no estoque da filial de destino.",
        cause="A transferência só entra no destino depois de recebida pela filial.",
        steps=(
            "Na filial de destino, acesse Estoque > Entradas > Receber transferência.",
            "Selecione a nota de transferência e confirme as quantidades.",
        ),
        solution=(
            "A filial de destino recebeu a nota em Estoque > Entradas > Receber transferência e "
            "o estoque foi atualizado."
        ),
        questions=(
            "Mandei produtos para outra loja e lá o saldo continua igual, falta algum passo?",
            "Como a filial confirma o recebimento de uma transferência?",
        ),
    ),
    Problem(
        slug="estoque-lote-validade-e310",
        product=ESTOQUE,
        category="Estoque",
        tags=("estoque", "lote", "validade"),
        titles=("Erro E-310 na entrada com lote e validade", "Não aceita lote na entrada"),
        complaints=(
            "Ao dar entrada na nota do fornecedor aparece o erro E-310 nos itens com lote.",
            "Não consigo informar lote e validade na entrada, o sistema recusa.",
        ),
        symptom="A entrada de nota recusa lote e validade com o erro E-310.",
        cause="O produto não está marcado como controlado por lote no cadastro.",
        steps=(
            "Abra o cadastro do produto.",
            "Marque 'controla lote e validade' e salve.",
            "Refaça a entrada da nota.",
        ),
        solution=(
            "Os produtos não estavam marcados como controlados por lote. Marcado no cadastro, a "
            "entrada aceitou lote e validade."
        ),
        questions=(
            "O recebimento da nota do fornecedor não aceita a data de vencimento dos itens.",
            "Como habilitar o controle de lote em um produto?",
        ),
    ),
)
