import { api, post, type ImportResult } from "./api";

/** Lets the app shell refresh after data changes elsewhere (e.g. the sample-data badge). */
export const DATA_CHANGED = "secondo:data-changed";
const announce = () => window.dispatchEvent(new Event(DATA_CHANGED));

export async function importCsv(file: Blob, filename: string): Promise<ImportResult> {
  const form = new FormData();
  form.append("file", file, filename);
  const result = await api<ImportResult>("/orders/import", { method: "POST", body: form });
  announce();
  return result;
}

/** Imports the bundled synthetic sales; the server marks the business as holding sample data. */
export async function importSampleSales(): Promise<ImportResult> {
  const result = await post<ImportResult>("/orders/import-sample");
  announce();
  return result;
}
