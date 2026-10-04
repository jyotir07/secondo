"use client";

import { AlertTriangle, Check, ChefHat, Info, RotateCcw, ShoppingBasket, Users, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Badge, Button, Card, Empty, ErrorState, Field, Loading, Notice, PageHeader, cx, inputClass } from "@/components/ui";
import { post, type Health, type KitchenPlan, type OrderList } from "@/lib/api";
import { formatDay, formatLongDay, formatTimestamp, num } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const STATUS_TONE = { draft: "amber", modified: "amber", approved: "green", rejected: "neutral" } as const;
const STATUS_LABEL = { draft: "Draft · needs review", modified: "Edited · needs approval", approved: "Approved", rejected: "Rejected" };
const isOpen = (p: KitchenPlan) => p.status === "draft" || p.status === "modified";

export default function PlanPage() {
  const health = useApi<Health>("/health");
  const plans = useApi<KitchenPlan[]>("/kitchen-plans");
  const orders = useApi<OrderList>("/orders?limit=1");
  const [confirmReject, setConfirmReject] = useState(false);
  const [selectedId, setSelectedId] = useState<string>();
  const [targetDate, setTargetDate] = useState("");
  const [edits, setEdits] = useState<Record<string, number>>({});
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<"generate" | "save" | "approve" | "reject">();
  const [error, setError] = useState<string>();
  const [flash, setFlash] = useState<string>();

  const list = plans.data ?? [];
  const plan = list.find((p) => p.id === selectedId) ?? list.find(isOpen) ?? list[0];
  const editable = plan ? isOpen(plan) : false;
  const dirty = plan ? plan.items.some((i) => edits[i.product_id] !== undefined && edits[i.product_id] !== i.final_quantity) : false;
  const qty = (pid: string, fallback: number) => edits[pid] ?? fallback;
  const totalUnits = plan?.items.reduce((s, i) => s + qty(i.product_id, i.final_quantity), 0) ?? 0;

  async function act(kind: NonNullable<typeof busy>, fn: () => Promise<KitchenPlan>, message: (p: KitchenPlan) => string) {
    setBusy(kind);
    setError(undefined);
    setFlash(undefined);
    try {
      const updated = await fn();
      await plans.reload();
      setSelectedId(updated.id);
      setEdits({});
      setNote("");
      setConfirmReject(false);
      setFlash(message(updated));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(undefined);
    }
  }

  const changedQuantities = () =>
    Object.fromEntries(plan!.items.filter((i) => edits[i.product_id] !== undefined && edits[i.product_id] !== i.final_quantity).map((i) => [i.product_id, edits[i.product_id]]));

  const generate = () =>
    act("generate", () => post<KitchenPlan>("/kitchen-plans/generate", { target_date: targetDate || null }), (p) => `Plan ready for ${formatLongDay(p.target_date)}. Review the quantities, then approve.`);
  const saveEdits = () =>
    act("save", () => post<KitchenPlan>(`/kitchen-plans/${plan!.id}/modify`, { quantities: changedQuantities(), note: note || null }), () => "Changes saved. The plan still needs approval.");
  const approve = () =>
    act("approve", async () => {
      // Approving with unsaved edits records them first, so the approved plan is what's on screen.
      if (dirty) await post(`/kitchen-plans/${plan!.id}/modify`, { quantities: changedQuantities(), note: note || null });
      return post<KitchenPlan>(`/kitchen-plans/${plan!.id}/approve`, { note: note || null });
    }, (p) => `Approved. This is the baking plan for ${formatLongDay(p.target_date)}.`);
  const reject = () =>
    act("reject", () => post<KitchenPlan>(`/kitchen-plans/${plan!.id}/reject`, { note: note || null }), () => "Plan rejected. Generate a fresh one when you're ready.");

  return (
    <>
      <PageHeader
        eyebrow="Decide · Act"
        title="Kitchen plan"
        description="A suggested bake list with the reason behind every number. Nothing is final until you approve it."
      />

      {orders.data?.total === 0 && (
        <div className="mb-6">
          <Notice icon={<Info className="size-4" />}>
            There&apos;s no sales history yet, so a plan would only contain pre-orders.{" "}
            <Link href="/orders" className="font-medium underline">Import sales on the Orders page</Link> first.
          </Notice>
        </div>
      )}

      <Card className="mb-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="sm:w-56">
            <Field label="Plan for" htmlFor="target" hint={targetDate ? undefined : "Defaults to the next day you're open"}>
              <input id="target" type="date" min={health.data?.today} value={targetDate} onChange={(e) => setTargetDate(e.target.value)} className={inputClass} />
            </Field>
          </div>
          <Button onClick={generate} busy={busy === "generate"} disabled={!!busy} icon={<ChefHat className="size-4" />} className="sm:mb-[22px]">
            Generate plan
          </Button>
          {targetDate && <Button variant="ghost" onClick={() => setTargetDate("")} className="sm:mb-[22px]">Use next open day</Button>}
        </div>
      </Card>

      {busy === "generate" && (
        <div className="mb-6">
          <Notice tone="neutral">Building the plan… forecasting each product. The first TabPFN run on a CPU can take up to a minute.</Notice>
        </div>
      )}
      {error && <div className="mb-6"><ErrorState message={error} /></div>}
      {flash && <div className="mb-6"><Notice tone="green" icon={<Check className="size-4" />}>{flash}</Notice></div>}

      {plans.loading && !plans.data ? (
        <Loading />
      ) : plans.error ? (
        <ErrorState message={plans.error} onRetry={plans.reload} />
      ) : !plan ? (
        <Card>
          <Empty title="No kitchen plans yet" icon={<ChefHat className="size-5" />}>
            Generate a plan above. It combines confirmed customer orders with the demand forecast. If you haven&apos;t imported sales yet, <Link href="/orders" className="text-forest underline">start on the Orders page</Link>.
          </Empty>
        </Card>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[1fr_320px]">
          <div className="min-w-0 space-y-6">
            <Card
              title={formatLongDay(plan.target_date)}
              description={`${num(totalUnits, 0)} units to prepare · forecast by ${plan.model_name.replace("_", " ")} · created ${formatTimestamp(plan.created_at)}`}
              actions={<Badge tone={STATUS_TONE[plan.status]}>{STATUS_LABEL[plan.status]}</Badge>}
              padded={false}
            >
              <ul className="divide-y divide-line">
                {plan.items.map((item) => {
                  const value = qty(item.product_id, item.final_quantity);
                  const changed = value !== item.recommended_quantity;
                  return (
                    <li key={item.product_id} className="grid gap-3 px-5 py-4 sm:grid-cols-[1fr_auto] sm:items-start">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-medium">{item.product_name}</span>
                          {item.confirmed_quantity > 0 && <Badge tone="sage">{item.confirmed_quantity} pre-ordered</Badge>}
                          {changed && <Badge tone="amber">suggested {item.recommended_quantity}</Badge>}
                        </div>
                        <p className="mt-1 text-sm leading-relaxed text-muted">{item.explanation}</p>
                      </div>
                      <div className="flex items-center gap-2 sm:justify-end">
                        {editable ? (
                          <>
                            <label htmlFor={`q-${item.product_id}`} className="sr-only">Quantity of {item.product_name}</label>
                            <input
                              id={`q-${item.product_id}`}
                              type="number"
                              min={0}
                              value={value}
                              onChange={(e) => setEdits({ ...edits, [item.product_id]: Math.max(0, Math.round(Number(e.target.value) || 0)) })}
                              className={cx(inputClass, "tabular h-10 w-20 text-right text-base font-medium", changed && "border-amber/50")}
                            />
                            {changed && (
                              <button
                                type="button"
                                title="Reset to suggestion"
                                aria-label={`Reset ${item.product_name} to suggestion`}
                                onClick={() => setEdits({ ...edits, [item.product_id]: item.recommended_quantity })}
                                className="rounded-md p-1.5 text-muted hover:bg-cream hover:text-forest"
                              >
                                <RotateCcw className="size-4" />
                              </button>
                            )}
                          </>
                        ) : (
                          <span className="tabular font-serif text-2xl text-forest">{value}</span>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>

              {editable ? (
                <div className="space-y-3 border-t border-line bg-cream/50 px-5 py-4">
                  <Field label="Note (optional)" htmlFor="note">
                    <input id="note" value={note} maxLength={1000} onChange={(e) => setNote(e.target.value)} className={inputClass} placeholder="e.g. Fewer croissants, the oven's being serviced" />
                  </Field>
                  <div className="flex flex-wrap gap-2">
                    <Button onClick={approve} busy={busy === "approve"} disabled={!!busy} icon={<Check className="size-4" />}>
                      {dirty ? "Save & approve" : "Approve plan"}
                    </Button>
                    {dirty && (
                      <Button variant="secondary" onClick={saveEdits} busy={busy === "save"} disabled={!!busy}>Save edits</Button>
                    )}
                    {!confirmReject && (
                      <Button variant="danger" onClick={() => setConfirmReject(true)} disabled={!!busy} icon={<X className="size-4" />}>Reject</Button>
                    )}
                  </div>
                  {confirmReject && (
                    <div className="flex flex-col gap-2 rounded-lg border border-danger/20 bg-danger-50 p-3 text-sm text-danger sm:flex-row sm:items-center sm:justify-between">
                      <span>Reject this plan? It stays in the history but can&apos;t be reopened. You can generate a new one.</span>
                      <span className="flex shrink-0 gap-2">
                        <Button variant="danger" onClick={reject} busy={busy === "reject"} disabled={!!busy}>Yes, reject</Button>
                        <Button variant="ghost" onClick={() => setConfirmReject(false)}>Keep it</Button>
                      </span>
                    </div>
                  )}
                </div>
              ) : (
                <div className="border-t border-line px-5 py-3 text-sm text-muted">
                  {plan.status === "approved" && plan.approved_at && <>Approved {formatTimestamp(plan.approved_at)}. Approved plans are kept as a record and can&apos;t be changed.</>}
                  {plan.status === "rejected" && <>Rejected{plan.reviewed_at && ` ${formatTimestamp(plan.reviewed_at)}`}. Generate a new plan for this date to try again.</>}
                  {plan.review_note && <p className="mt-1 text-ink">Note: {plan.review_note}</p>}
                </div>
              )}
            </Card>

            {plan.customer_requests.length > 0 && (
              <Card title="Customer orders in this plan" actions={<Users className="size-5 text-sage" aria-hidden />} padded={false}>
                <ul className="divide-y divide-line">
                  {plan.customer_requests.map((r) => (
                    <li key={r.order_id} className="px-5 py-3 text-sm">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{r.customer_name ?? "Customer"}</span>
                        <span className="text-muted">{r.quantity} × {r.product_name}</span>
                        {r.dietary_constraints.map((d) => <Badge key={d} tone="amber">{d}</Badge>)}
                      </div>
                      {r.notes && <p className="mt-0.5 text-muted">{r.notes}</p>}
                    </li>
                  ))}
                </ul>
              </Card>
            )}
          </div>

          <div className="space-y-6">
            {plan.warnings.length > 0 && (
              <Card title="Warnings">
                <ul className="space-y-2">
                  {plan.warnings.map((w, i) => (
                    <li key={i}>
                      <Notice tone={w.severity === "warning" ? "amber" : "neutral"} icon={w.severity === "warning" ? <AlertTriangle className="size-4" /> : <Info className="size-4" />}>
                        {w.message}
                      </Notice>
                    </li>
                  ))}
                </ul>
              </Card>
            )}

            {plan.explanations.length > 0 && (
              <Card title="Why these numbers">
                <ul className="space-y-2 text-sm leading-relaxed text-muted">
                  {plan.explanations.map((e) => <li key={e}>{e}</li>)}
                </ul>
              </Card>
            )}

            <Card title="Ingredients needed" description="For the approved quantities" actions={<ShoppingBasket className="size-5 text-sage" aria-hidden />}>
              {plan.ingredient_needs.length === 0 ? (
                <p className="text-sm text-muted">No recipes recorded for these products.</p>
              ) : (
                <ul className="tabular divide-y divide-line text-sm">
                  {plan.ingredient_needs.map((n) => (
                    <li key={`${n.ingredient}-${n.unit}`} className="flex justify-between py-1.5">
                      <span>{n.ingredient}</span>
                      <span className="font-medium">{num(n.quantity, 2)} {n.unit}</span>
                    </li>
                  ))}
                </ul>
              )}
              {dirty && <p className="mt-2 text-xs text-amber">Save your edits to recalculate.</p>}
            </Card>

            <Card title="Plan history" padded={false}>
              <ul className="divide-y divide-line">
                {list.slice(0, 12).map((p) => (
                  <li key={p.id}>
                    <button
                      type="button"
                      onClick={() => { setSelectedId(p.id); setEdits({}); setFlash(undefined); setConfirmReject(false); }}
                      className={cx("flex w-full items-center justify-between gap-2 px-5 py-2.5 text-left text-sm hover:bg-cream", p.id === plan.id && "bg-forest-50")}
                    >
                      <span>{formatDay(p.target_date)}</span>
                      <Badge tone={STATUS_TONE[p.status]}>{p.status}</Badge>
                    </button>
                  </li>
                ))}
              </ul>
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
