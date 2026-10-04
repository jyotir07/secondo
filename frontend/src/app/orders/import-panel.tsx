"use client";

import { CheckCircle2, Database, FileUp } from "lucide-react";
import { useRef, useState } from "react";
import { Button, Card, ErrorState, Notice } from "@/components/ui";
import type { ImportResult } from "@/lib/api";
import { importCsv, importSampleSales } from "@/lib/actions";
import { formatShortDay } from "@/lib/format";

export function ImportPanel({ onImported }: { onImported: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<"file" | "sample">();
  const [result, setResult] = useState<ImportResult>();
  const [error, setError] = useState<string>();

  async function run(kind: "file" | "sample", fn: () => Promise<ImportResult>) {
    setBusy(kind);
    setError(undefined);
    setResult(undefined);
    try {
      setResult(await fn());
      onImported();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(undefined);
      if (input.current) input.current.value = "";
    }
  }

  return (
    <Card title="Import sales history" description="CSV with date, product and quantity columns">
      <input
        ref={input}
        type="file"
        accept=".csv,text/csv"
        className="sr-only"
        aria-label="Sales CSV file"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void run("file", () => importCsv(file, file.name));
        }}
      />
      <div className="flex flex-wrap gap-2">
        <Button busy={busy === "file"} disabled={!!busy} onClick={() => input.current?.click()} icon={<FileUp className="size-4" />}>
          Upload CSV
        </Button>
        <Button variant="secondary" busy={busy === "sample"} disabled={!!busy} onClick={() => run("sample", importSampleSales)} icon={<Database className="size-4" />}>
          Use synthetic sample
        </Button>
      </div>
      <p className="mt-3 text-xs leading-relaxed text-muted">
        Accepted headers: <code>date</code>, <code>product_name</code> or <code>product_id</code>, <code>quantity_sold</code>.
        Optional: <code>customer</code>, <code>notes</code>, <code>status</code>. Rows already imported are skipped, so re-uploading is safe.
      </p>

      {error && <div className="mt-4"><ErrorState message={error} /></div>}
      {result && (
        <div className="mt-4 space-y-2">
          <Notice tone={result.imported > 0 ? "green" : "neutral"} icon={<CheckCircle2 className="size-4" />}>
            Imported <strong>{result.imported}</strong> of {result.total_rows} rows
            {result.first_date && result.last_date && <> ({formatShortDay(result.first_date)} – {formatShortDay(result.last_date)})</>}.
            {result.duplicates > 0 && <> {result.duplicates} already saved, skipped.</>}
            {result.skipped_zero_quantity > 0 && <> {result.skipped_zero_quantity} zero-quantity rows ignored.</>}
          </Notice>
          {result.errors.length > 0 && (
            <div className="rounded-lg border border-amber/20 bg-amber-50 p-3 text-sm text-amber">
              <p className="font-medium">{result.errors.length} row{result.errors.length > 1 ? "s" : ""} need fixing in the file:</p>
              <ul className="mt-1.5 max-h-40 space-y-0.5 overflow-y-auto text-xs">
                {result.errors.map((e) => (
                  <li key={e.line}>Line {e.line}: {e.message}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
