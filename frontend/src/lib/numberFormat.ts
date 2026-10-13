/** Numbers for reading, with `Intl`, in the interface language. */

/**
 * Cost in US dollars for reading. Embedding runs cost fractions of a cent, so small values keep
 * 4 to 6 decimals ("US$ 0,000048"); from one cent up, 2 to 4. `null` (unknown price) is "—".
 */
export function formatUsd(value: number | null, locale: string): string {
  if (value === null) {
    return "—";
  }
  const small = value > 0 && value < 0.01;
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: small ? 4 : 2,
    maximumFractionDigits: small ? 6 : 4,
  }).format(value);
}

/** A whole number with the locale's grouping ("51.000"). */
export function formatCount(value: number, locale: string): string {
  return new Intl.NumberFormat(locale).format(value);
}
