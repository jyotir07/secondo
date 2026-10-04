"use client";

import { ChevronLeft, ChevronRight, ReceiptText } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, Empty, ErrorState, Loading, PageHeader, inputClass } from "@/components/ui";
import type { Health, OrderList, Product } from "@/lib/api";
import { SOURCE_LABEL, addDays, formatDay } from "@/lib/format";
import { useApi } from "@/lib/use-api";
import { ImportPanel } from "./import-panel";
import { ManualForm } from "./manual-form";
import { MessagePanel } from "./message-panel";

const PAGE = 25;
const STATUS_TONE = { pending: "amber", confirmed: "sage", completed: "neutral", cancelled: "red" } as const;

export default function OrdersPage() {
  const health = useApi<Health>("/health");
  const products = useApi<Product[]>("/products");
  const [filters, setFilters] = useState({ product_id: "", source: "", status: "", start: "", end: "" });
  const [offset, setOffset] = useState(0);

  const query = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
  Object.entries(filters).forEach(([k, v]) => v && query.set(k, v));
  const orders = useApi<OrderList>(`/orders?${query}`);

  const setFilter = (key: keyof typeof filters, value: string) => {
    setFilters({ ...filters, [key]: value });
    setOffset(0);
  };
  const active = (products.data ?? []).filter((p) => p.active);
  const total = orders.data?.total ?? 0;
  const filtered = Object.values(filters).some(Boolean);

  return (
    <>
      <PageHeader
        eyebrow="Understand"
        title="Orders"
        description="Everything the kitchen has sold or promised. Past sales feed the forecast; upcoming orders are always baked first."
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-6">
          {products.error ? (
            <ErrorState message={products.error} onRetry={products.reload} />
          ) : (
            <MessagePanel products={active} onSaved={orders.reload} />
          )}
        </div>
        <div className="space-y-6">
          <ImportPanel onImported={orders.reload} />
          {health.data && active.length > 0 && (
            <ManualForm products={active} defaultDate={addDays(health.data.today, 1)} onSaved={orders.reload} />
          )}
        </div>
      </div>

      <Card className="mt-8" title="All orders" description={orders.data ? `${total} order line${total === 1 ? "" : "s"}${filtered ? " match" : ""}` : undefined} padded={false}>
        <div className="grid grid-cols-2 gap-2 border-b border-line px-5 py-3 md:grid-cols-5">
          <select aria-label="Filter by product" value={filters.product_id} onChange={(e) => setFilter("product_id", e.target.value)} className={inputClass}>
            <option value="">All products</option>
            {(products.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <select aria-label="Filter by source" value={filters.source} onChange={(e) => setFilter("source", e.target.value)} className={inputClass}>
            <option value="">All sources</option>
            {Object.entries(SOURCE_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <select aria-label="Filter by status" value={filters.status} onChange={(e) => setFilter("status", e.target.value)} className={inputClass}>
            <option value="">All statuses</option>
            {Object.keys(STATUS_TONE).map((s) => <option key={s} value={s}>{s[0].toUpperCase() + s.slice(1)}</option>)}
          </select>
          <input aria-label="From date" type="date" value={filters.start} onChange={(e) => setFilter("start", e.target.value)} className={inputClass} />
          <input aria-label="To date" type="date" value={filters.end} onChange={(e) => setFilter("end", e.target.value)} className={inputClass} />
        </div>

        {orders.loading && !orders.data ? (
          <Loading className="px-5" />
        ) : orders.error ? (
          <div className="p-5"><ErrorState message={orders.error} onRetry={orders.reload} /></div>
        ) : total === 0 ? (
          <Empty title={filtered ? "No orders match these filters" : "No orders yet"} icon={<ReceiptText className="size-5" />}
            action={filtered && <Button variant="secondary" onClick={() => setFilters({ product_id: "", source: "", status: "", start: "", end: "" })}>Clear filters</Button>}>
            {!filtered && "Import your sales history or paste a customer message above."}
          </Empty>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-sm">
                <thead>
                  <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
                    <th className="px-5 py-2.5 font-medium">Date</th>
                    <th className="px-3 py-2.5 font-medium">Product</th>
                    <th className="px-3 py-2.5 text-right font-medium">Qty</th>
                    <th className="px-3 py-2.5 font-medium">Customer</th>
                    <th className="px-3 py-2.5 font-medium">Source</th>
                    <th className="px-5 py-2.5 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {orders.data!.orders.map((o) => (
                    <tr key={o.id} className="align-top hover:bg-cream/60">
                      <td className="whitespace-nowrap px-5 py-2.5">{formatDay(o.order_date, { year: "numeric" })}</td>
                      <td className="px-3 py-2.5">
                        {o.product_name}
                        {o.notes && <p className="mt-0.5 max-w-xs text-xs text-muted">{o.notes}</p>}
                      </td>
                      <td className="tabular px-3 py-2.5 text-right font-medium">{o.quantity}</td>
                      <td className="px-3 py-2.5 text-muted">{o.customer_name ?? "—"}</td>
                      <td className="px-3 py-2.5">
                        <span title={o.original_input ?? undefined}>
                          <Badge tone={o.source === "message" ? "sage" : "neutral"}>{SOURCE_LABEL[o.source]}</Badge>
                        </span>
                      </td>
                      <td className="px-5 py-2.5"><Badge tone={STATUS_TONE[o.status]}>{o.status}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="flex items-center justify-between border-t border-line px-5 py-3 text-sm text-muted">
              <span className="tabular">{offset + 1}–{Math.min(offset + PAGE, total)} of {total}</span>
              <div className="flex gap-1">
                <Button variant="secondary" aria-label="Previous page" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                  <ChevronLeft className="size-4" />
                </Button>
                <Button variant="secondary" aria-label="Next page" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>
                  <ChevronRight className="size-4" />
                </Button>
              </div>
            </div>
          </>
        )}
      </Card>
    </>
  );
}
