// Fictional sample code of the Vértice ERP, used only by the KnoBridge evaluation set.

export const MULTA_ATRASO = 0.02;
export const JUROS_AO_DIA = 0.00033;
export const PRAZO_MAXIMO_REEMISSAO_DIAS = 30;

export interface Encargos {
  multa: number;
  juros: number;
  total: number;
}

/** Late fee (2%) plus daily interest (0.033% a day) on a reissued slip. */
export function calcularEncargos(valor: number, diasAtraso: number): Encargos {
  if (diasAtraso <= 0) {
    return { multa: 0, juros: 0, total: valor };
  }
  const multa = arredondar(valor * MULTA_ATRASO);
  const juros = arredondar(valor * JUROS_AO_DIA * diasAtraso);
  return { multa, juros, total: arredondar(valor + multa + juros) };
}

export function podeReemitir(pagoEm: Date | null, novoVencimento: Date, hoje: Date): boolean {
  const limite = new Date(hoje.getTime() + PRAZO_MAXIMO_REEMISSAO_DIAS * 24 * 3600 * 1000);
  return pagoEm === null && novoVencimento <= limite;
}

function arredondar(valor: number): number {
  return Math.round(valor * 100) / 100;
}
