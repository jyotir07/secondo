const parseDay = (iso: string) => {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d);
};

export const formatDay = (iso: string, opts: Intl.DateTimeFormatOptions = {}) =>
  parseDay(iso).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", ...opts });

export const formatLongDay = (iso: string) =>
  parseDay(iso).toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long" });

export const formatShortDay = (iso: string) =>
  parseDay(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });

export const formatTimestamp = (iso: string) =>
  new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export const addDays = (iso: string, days: number) => {
  const d = parseDay(iso);
  d.setDate(d.getDate() + days);
  return toIso(d);
};

export const toIso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export const num = (n: number, digits = 1) =>
  n.toLocaleString("en-IN", { maximumFractionDigits: digits, minimumFractionDigits: 0 });

export const SOURCE_LABEL: Record<string, string> = {
  csv_import: "CSV import",
  manual: "Manual",
  message: "Message",
};

export const PROVIDER_LABEL: Record<string, string> = {
  historical_average: "Historical average",
  weekday_average: "Weekday average",
  tabpfn: "TabPFN",
  rules: "Rule-based parser",
  ollama: "Gemma via Ollama",
};
