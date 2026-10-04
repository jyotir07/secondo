"use client";

import { Cpu, MessageSquareText, Plus, Sparkles, Trash2 } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, ErrorState, Field, Notice, inputClass } from "@/components/ui";
import { ApiError, post, type ExtractionResult, type OrderCreate, type OrderCreateResult, type Product } from "@/lib/api";
import { PROVIDER_LABEL } from "@/lib/format";

const EXAMPLE =
  "Hi! Can I get 2 sourdough loaves and half a dozen cinnamon rolls for Saturday? Eggless please, it's for my mum. I'll pick up around 10am. - Priya";

interface Line {
  product_id: string;
  quantity: number;
}

export function MessagePanel({ products, onSaved }: { products: Product[]; onSaved: () => void }) {
  const [text, setText] = useState("");
  const [extracting, setExtracting] = useState(false);
  const [result, setResult] = useState<ExtractionResult>();
  const [error, setError] = useState<string>();

  // Editable review state, seeded from the extraction.
  const [lines, setLines] = useState<Line[]>([]);
  const [orderDate, setOrderDate] = useState("");
  const [customer, setCustomer] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [duplicate, setDuplicate] = useState(false);
  const [saved, setSaved] = useState<string>();

  async function extract() {
    setExtracting(true);
    setError(undefined);
    setSaved(undefined);
    setDuplicate(false);
    try {
      const r = await post<ExtractionResult>("/orders/extract", { text });
      setResult(r);
      setLines(r.items.filter((i) => i.product_id).map((i) => ({ product_id: i.product_id!, quantity: i.quantity })));
      setOrderDate(r.order_date ?? "");
      setCustomer(r.customer_name ?? "");
      setNotes([r.dietary_constraints.length ? r.dietary_constraints.join(", ") : "", r.notes ?? ""].filter(Boolean).join(". "));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setExtracting(false);
    }
  }

  async function save(allowDuplicate = false) {
    if (!result) return;
    setSaving(true);
    setError(undefined);
    try {
      const body: OrderCreate = {
        order_date: orderDate,
        items: lines.filter((l) => l.quantity > 0),
        customer_name: customer.trim() || null,
        dietary_constraints: result.dietary_constraints,
        notes: notes.trim() || null,
        source: "message",
        original_input: result.original_input,
        extraction_confidence: result.confidence,
        allow_duplicate: allowDuplicate,
      };
      const r = await post<OrderCreateResult>("/orders", body);
      setSaved(`Saved ${r.created.length} order line${r.created.length > 1 ? "s" : ""}${customer ? ` for ${customer}` : ""}.`);
      setResult(undefined);
      setText("");
      setDuplicate(false);
      onSaved();
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) setDuplicate(true);
      else setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  }

  const canSave = !!orderDate && lines.some((l) => l.quantity > 0 && l.product_id);
  const confidenceTone = !result ? "neutral" : result.confidence >= 0.8 ? "green" : result.confidence >= 0.6 ? "amber" : "red";

  return (
    <Card
      title="Read a customer message"
      description="Paste a WhatsApp or SMS order. You check the result before anything is saved."
      actions={<MessageSquareText className="size-5 text-sage" aria-hidden />}
    >
      <label htmlFor="message" className="sr-only">Customer message</label>
      <textarea
        id="message"
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={4}
        maxLength={5000}
        placeholder="e.g. Hi, 2 sourdough loaves and 6 croissants for tomorrow morning please. - Anil"
        className={`${inputClass} h-auto resize-y py-2 leading-relaxed`}
      />
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button onClick={extract} busy={extracting} disabled={!text.trim()} icon={<Sparkles className="size-4" />}>
          Extract order
        </Button>
        {!text && (
          <Button variant="ghost" onClick={() => setText(EXAMPLE)}>
            Paste an example
          </Button>
        )}
      </div>

      {error && <div className="mt-4"><ErrorState message={error} /></div>}
      {saved && <div className="mt-4"><Notice tone="green">{saved}</Notice></div>}

      {result && (
        <div className="mt-5 border-t border-line pt-5">
          <div className="mb-4 flex flex-wrap items-center gap-2 text-xs">
            <Badge tone={result.fallback_used ? "amber" : "sage"}>
              <Cpu className="size-3" aria-hidden />
              {PROVIDER_LABEL[result.provider] ?? result.provider}
              {result.model && ` · ${result.model}`}
            </Badge>
            <Badge tone={confidenceTone}>{Math.round(result.confidence * 100)}% confidence</Badge>
            {result.latency_ms != null && <span className="text-muted">{result.latency_ms} ms</span>}
          </div>
          {result.fallback_used && result.fallback_reason && (
            <div className="mb-3"><Notice>Fallback used: {result.fallback_reason}</Notice></div>
          )}
          {result.warnings.length > 0 && (
            <ul className="mb-4 space-y-1 text-sm text-amber">
              {result.warnings.map((w) => <li key={w}>• {w}</li>)}
            </ul>
          )}

          <div className="space-y-2">
            {lines.map((l, idx) => (
              <div key={idx} className="flex items-center gap-2">
                <select
                  aria-label="Product"
                  value={l.product_id}
                  onChange={(e) => setLines(lines.map((x, j) => (j === idx ? { ...x, product_id: e.target.value } : x)))}
                  className={inputClass}
                >
                  {products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
                <input
                  aria-label="Quantity"
                  type="number"
                  min={1}
                  value={l.quantity}
                  onChange={(e) => setLines(lines.map((x, j) => (j === idx ? { ...x, quantity: Number(e.target.value) } : x)))}
                  className={`${inputClass} tabular w-20 text-right`}
                />
                <button
                  type="button"
                  aria-label="Remove line"
                  onClick={() => setLines(lines.filter((_, j) => j !== idx))}
                  className="rounded-md p-2 text-muted hover:bg-danger-50 hover:text-danger"
                >
                  <Trash2 className="size-4" />
                </button>
              </div>
            ))}
            <Button
              variant="ghost"
              onClick={() => products[0] && setLines([...lines, { product_id: products[0].id, quantity: 1 }])}
              icon={<Plus className="size-4" />}
            >
              Add item
            </Button>
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <Field label="Date needed" htmlFor="msg-date">
              <input id="msg-date" type="date" value={orderDate} onChange={(e) => setOrderDate(e.target.value)} className={inputClass} />
            </Field>
            <Field label="Customer" htmlFor="msg-customer">
              <input id="msg-customer" value={customer} onChange={(e) => setCustomer(e.target.value)} className={inputClass} placeholder="Name" />
            </Field>
            <div className="sm:col-span-2">
              <Field label="Notes for the kitchen" htmlFor="msg-notes">
                <input id="msg-notes" value={notes} onChange={(e) => setNotes(e.target.value)} className={inputClass} />
              </Field>
            </div>
          </div>

          {duplicate ? (
            <div className="mt-4 space-y-2">
              <Notice>An identical order for this customer and date is already saved.</Notice>
              <div className="flex gap-2">
                <Button variant="secondary" onClick={() => save(true)} busy={saving}>Save anyway</Button>
                <Button variant="ghost" onClick={() => { setResult(undefined); setDuplicate(false); }}>Discard</Button>
              </div>
            </div>
          ) : (
            <div className="mt-4 flex flex-wrap gap-2">
              <Button onClick={() => save()} busy={saving} disabled={!canSave}>Save order</Button>
              <Button variant="ghost" onClick={() => setResult(undefined)}>Discard</Button>
              {!orderDate && <span className="self-center text-xs text-amber">Pick a date to save.</span>}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
