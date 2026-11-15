/** Amounts from the API are integer minor units (tyiyn). 494000 -> "4 940.00 KGS". */
export function formatMoney(minor: number, currency = "KGS"): string {
  const negative = minor < 0;
  const abs = Math.abs(Math.round(minor));
  const whole = Math.floor(abs / 100);
  const frac = String(abs % 100).padStart(2, "0");
  const grouped = String(whole).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  return `${negative ? "-" : ""}${grouped}.${frac} ${currency}`;
}
