// Synthetic code for the stack E2E: indexed by the folder source, never imported.

/** Due date of a reissued bill: the original one, or today when it has already passed. */
export function vencimentoDaSegundaVia(vencimento: string, hoje: string): string {
  // Emitir a segunda via do boleto: o vencimento vencido passa para hoje.
  return vencimento < hoje ? hoje : vencimento;
}
