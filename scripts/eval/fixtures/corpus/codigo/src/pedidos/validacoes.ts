// Fictional sample code of the Vértice ERP, used only by the KnoBridge evaluation set.
import type { Banco } from "../banco";
import { calcularExposicao, excedeLimite, limiteEfetivo } from "../credito/exposicao";

export type Resultado =
  | { tipo: "aceito" }
  | { tipo: "recusado"; codigo: string }
  | { tipo: "aguardando_credito"; codigo: string };

export interface Pedido {
  clienteId: number;
  valorTotal: number;
}

const DIAS_ATRASO_BLOQUEIO = 30;

/** Rules checked when an order is saved, in order (docs: interno-validacoes-do-pedido.md). */
export async function validarPedido(banco: Banco, pedido: Pedido, hoje: Date): Promise<Resultado> {
  const cliente = await banco.cliente(pedido.clienteId);
  if (cliente.bloqueado) {
    return { tipo: "recusado", codigo: "VAL-PED-010" };
  }
  const maiorAtraso = await banco.maiorAtrasoEmDias(pedido.clienteId, hoje);
  if (maiorAtraso > DIAS_ATRASO_BLOQUEIO) {
    return { tipo: "aguardando_credito", codigo: "VAL-PED-014" };
  }
  const exposicao = await calcularExposicao(banco, pedido.clienteId);
  const limite = limiteEfetivo(cliente.limiteCredito, cliente.clienteDesde, hoje);
  if (excedeLimite(exposicao, pedido.valorTotal, limite)) {
    return { tipo: "aguardando_credito", codigo: "VAL-PED-020" };
  }
  return { tipo: "aceito" };
}
