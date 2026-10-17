// Fictional sample code of the Vértice ERP, used only by the KnoBridge evaluation set.
import type { Sefaz } from "./sefaz";

export type Acao = "sincronizar_autorizacao" | "retransmitir" | "corrigir_cadastro" | "abrir_chamado";

/** What the invoice screen offers after each SEFAZ rejection code. */
export const ACOES_POR_REJEICAO: Record<number, Acao> = {
  204: "sincronizar_autorizacao",
  539: "sincronizar_autorizacao",
  225: "corrigir_cadastro",
  999: "abrir_chamado",
};

/**
 * Rejection 539 means SEFAZ already has an invoice with this number: the first transmission got
 * there and the answer was lost. Fetch the protocol instead of creating a new invoice (12.3).
 */
export async function tratarRejeicao(sefaz: Sefaz, notaId: number, codigo: number): Promise<Acao> {
  const acao = ACOES_POR_REJEICAO[codigo] ?? "retransmitir";
  if (acao === "sincronizar_autorizacao") {
    const protocolo = await sefaz.consultarProtocolo(notaId);
    if (protocolo === null) {
      return "retransmitir";
    }
    await sefaz.gravarAutorizacao(notaId, protocolo);
  }
  return acao;
}
