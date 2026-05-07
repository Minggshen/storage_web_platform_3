export function formatNumber(value?: number | null, fractionDigits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "--";
  return new Intl.NumberFormat("zh-CN", { maximumFractionDigits: fractionDigits, minimumFractionDigits: fractionDigits }).format(value);
}

export function formatDateTime(value?: string | null): string {
  if (!value) return "--";
  return value.replace("T", " ");
}
