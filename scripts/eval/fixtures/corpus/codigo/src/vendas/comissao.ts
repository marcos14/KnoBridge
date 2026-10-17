// Fictional sample code of the Vértice ERP, used only by the KnoBridge evaluation set.
import type { Banco } from "../banco";

export interface LinhaComissao {
  vendedorId: number;
  tituloId: number;
  percentual: number;
  valor: number;
}

/**
 * Commission is paid on received slips, not on invoiced value (card EVAL-C-005): it runs on the
 * first day of the month over the slips paid in the previous month (the competence).
 */
export async function calcularComissao(banco: Banco, competencia: Date): Promise<LinhaComissao[]> {
  const recebidos = await banco.titulosPagosNoMes(competencia);
  return recebidos.map((titulo) => ({
    vendedorId: titulo.vendedorId,
    tituloId: titulo.id,
    percentual: titulo.percentualComissao,
    valor: Math.round(titulo.valor * titulo.percentualComissao) / 100,
  }));
}

/** A return after payment reverses the commission in the next competence. */
export function estornar(linha: LinhaComissao): LinhaComissao {
  return { ...linha, valor: -linha.valor };
}
