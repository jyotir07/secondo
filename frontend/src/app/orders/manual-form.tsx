"use client";

import { PencilLine } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Button, Card, ErrorState, Field, Notice, inputClass } from "@/components/ui";
import { ApiError, post, type OrderCreateResult, type Product } from "@/lib/api";

export function ManualForm({ products, defaultDate, onSaved }: { products: Product[]; defaultDate: string; onSaved: () => void }) {
  const [productId, setProductId] = useState("");
  const [quantity, setQuantity] = useState(1);
  const [date, setDate] = useState("");
  const [customer, setCustomer] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string>();
  const [saved, setSaved] = useState<string>();

  const effectiveProduct = productId || products[0]?.id || "";
  const effectiveDate = date || defaultDate;

  async function submit(e: FormEvent, allowDuplicate = false) {
    e.preventDefault();
    setSaving(true);
    setError(undefined);
    setSaved(undefined);
    try {
      await post<OrderCreateResult>("/orders", {
        order_date: effectiveDate,
        items: [{ product_id: effectiveProduct, quantity }],
        customer_name: customer.trim() || null,
        notes: notes.trim() || null,
        source: "manual",
        allow_duplicate: allowDuplicate,
      });
      const name = products.find((p) => p.id === effectiveProduct)?.name;
      setSaved(`Saved ${quantity} × ${name}.`);
      setQuantity(1);
      setCustomer("");
      setNotes("");
      onSaved();
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 409
          ? "This exact order is already saved. Change the quantity or notes if it's a separate order."
          : err instanceof Error ? err.message : String(err),
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card title="Add an order by hand" description="For phone calls and walk-in requests" actions={<PencilLine className="size-5 text-sage" aria-hidden />}>
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
        <Field label="Product" htmlFor="m-product">
          <select id="m-product" value={effectiveProduct} onChange={(e) => setProductId(e.target.value)} className={inputClass} required>
            {products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </Field>
        <Field label="Quantity" htmlFor="m-qty">
          <input id="m-qty" type="number" min={1} max={10000} required value={quantity} onChange={(e) => setQuantity(Number(e.target.value))} className={`${inputClass} tabular`} />
        </Field>
        <Field label="Date needed" htmlFor="m-date">
          <input id="m-date" type="date" required value={effectiveDate} onChange={(e) => setDate(e.target.value)} className={inputClass} />
        </Field>
        <Field label="Customer (optional)" htmlFor="m-customer">
          <input id="m-customer" value={customer} maxLength={120} onChange={(e) => setCustomer(e.target.value)} className={inputClass} />
        </Field>
        <div className="sm:col-span-2">
          <Field label="Notes (optional)" htmlFor="m-notes">
            <input id="m-notes" value={notes} maxLength={1000} onChange={(e) => setNotes(e.target.value)} className={inputClass} placeholder="e.g. less sweet, pick up 9am" />
          </Field>
        </div>
        <div className="sm:col-span-2">
          <Button type="submit" busy={saving} disabled={!effectiveProduct || quantity < 1}>Save order</Button>
        </div>
      </form>
      {error && <div className="mt-4"><ErrorState message={error} /></div>}
      {saved && <div className="mt-4"><Notice tone="green">{saved}</Notice></div>}
    </Card>
  );
}
