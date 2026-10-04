import { api, ApiError, type ImportResult } from "./api";

export async function importCsv(file: Blob, filename: string): Promise<ImportResult> {
  const form = new FormData();
  form.append("file", file, filename);
  return api<ImportResult>("/orders/import", { method: "POST", body: form });
}

/** Imports the bundled synthetic sales file through the same path a real upload takes. */
export async function importSampleSales(): Promise<ImportResult> {
  const res = await fetch("/api/orders/sample-csv", { cache: "no-store" });
  if (!res.ok) throw new ApiError("The sample sales file is missing on the server.", res.status);
  return importCsv(await res.blob(), "synthetic_bakery_sales.csv");
}
