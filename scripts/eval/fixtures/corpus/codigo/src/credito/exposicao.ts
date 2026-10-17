// Fictional sample code of the Vértice ERP, used only by the KnoBridge evaluation set.
import type { Banco } from "../banco";

export const TOLERANCIA_CLIENTE_ANTIGO = 0.05;
export const ANOS_CLIENTE_ANTIGO = 2;

export interface Exposicao {
  titulosEmAberto: number;
  pedidosNaoFaturados: number;
  total: number;
}

/** Credit exposure: open receivables plus orders not invoiced yet. */
export async function calcularExposicao(banco: Banco, clienteId: number): Promise<Exposicao> {
  const titulosEmAberto = await banco.somar(
    "SELECT coalesce(sum(valor), 0) FROM titulos_receber WHERE cliente_id = $1 AND pago_em IS NULL",
    [clienteId],
  );
  const pedidosNaoFaturados = await banco.somar(
    "SELECT coalesce(sum(valor_total), 0) FROM pedidos WHERE cliente_id = $1 AND situacao IN ('aberto', 'aguardando_credito')",
    [clienteId],
  );
  return { titulosEmAberto, pedidosNaoFaturados, total: titulosEmAberto + pedidosNaoFaturados };
}

/** Customers older than two years get a 5% tolerance above the limit (card EVAL-C-001). */
export function limiteEfetivo(limiteCredito: number, clienteDesde: Date, hoje: Date): number {
  const anos = (hoje.getTime() - clienteDesde.getTime()) / (365.25 * 24 * 3600 * 1000);
  return anos >= ANOS_CLIENTE_ANTIGO ? limiteCredito * (1 + TOLERANCIA_CLIENTE_ANTIGO) : limiteCredito;
}

export function excedeLimite(exposicao: Exposicao, valorPedido: number, limite: number): boolean {
  return exposicao.total + valorPedido > limite;
}
