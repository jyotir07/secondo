"use client";

import { AlertTriangle, ArrowRight, Check, ChefHat, Database, MessageSquareText, ReceiptText } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Badge, Button, Card, Empty, ErrorState, Loading, Notice, PageHeader, Stat, cx } from "@/components/ui";
import type { ForecastResponse, Health, KitchenPlan, OrderList } from "@/lib/api";
import { importSampleSales } from "@/lib/actions";
import { SOURCE_LABEL, formatDay, formatLongDay, formatTimestamp, num } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const PLAN_TONE = { draft: "amber", modified: "amber", approved: "green", rejected: "neutral" } as const;

export default function OverviewPage() {
  const health = useApi<Health>("/health");
  const orders = useApi<OrderList>("/orders?limit=1000");
  const plans = useApi<KitchenPlan[]>("/kitchen-plans");
  const forecast = useApi<ForecastResponse>("/forecasts?history_days=7");
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string>();

  const today = health.data?.today;
  const all = orders.data?.orders ?? [];
  const todays = all.filter((o) => o.order_date === today && o.status !== "cancelled");
  const preorders = all.filter((o) => today && o.order_date >= today && (o.status === "pending" || o.status === "confirmed"));
  const pending = (plans.data ?? []).filter((p) => p.status === "draft" || p.status === "modified");
  const latestPlan = plans.data?.[0];
  // A saved forecast for a day that has passed is history, not an expectation.
  const upcoming = today && forecast.data?.target_date && forecast.data.target_date >= today ? forecast.data : undefined;
  const expected = upcoming?.forecasts.reduce((s, f) => s + f.predicted_quantity, 0);
  const recent = [...all].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 6);
  const hasHistory = (orders.data?.total ?? 0) > 0;
  const loading = orders.loading || plans.loading;

  async function loadSample() {
    setImporting(true);
    setImportError(undefined);
    try {
      await importSampleSales();
      await Promise.all([orders.reload(), forecast.reload()]);
    } catch (e) {
      setImportError(e instanceof Error ? e.message : String(e));
    } finally {
      setImporting(false);
    }
  }

  if (health.error) {
    return (
      <>
        <PageHeader title="Good to see you." />
        <ErrorState message={health.error} onRetry={health.reload} />
        <p className="mt-4 text-sm text-muted">
          Start the API with <code className="rounded bg-line/60 px-1.5 py-0.5">uv run uvicorn app.main:create_app --factory</code> inside <code>backend/</code>.
        </p>
      </>
    );
  }

  const steps = [
    { done: hasHistory, label: "Bring in past sales", href: "/orders", icon: Database },
    { done: preorders.length > 0, label: "Add upcoming customer orders", href: "/orders", icon: MessageSquareText },
    { done: (plans.data?.length ?? 0) > 0, label: "Generate the kitchen plan", href: "/plan", icon: ChefHat },
    { done: (plans.data ?? []).some((p) => p.status === "approved"), label: "Review and approve it", href: "/plan", icon: Check },
  ];

  return (
    <>
      <PageHeader
        eyebrow={today ? formatLongDay(today) : undefined}
        title="What does the kitchen need?"
        description="Secondo turns your sales history and customer messages into a baking plan you approve. Nothing is baked on a guess you can't see."
        actions={
          hasHistory && (
            <Link href="/plan">
              <Button icon={<ChefHat className="size-4" />}>Open kitchen plan</Button>
            </Link>
          )
        }
      />

      {!loading && !hasHistory && (
        <Card className="mb-8">
          <div className="grid gap-6 md:grid-cols-[1.2fr_1fr] md:items-center">
            <div>
              <h2 className="font-serif text-2xl text-forest">Start with what you already sold.</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted">
                Forecasts come from your own history. Upload a sales CSV from your notebook or spreadsheet, or try
                Secondo with four months of <strong className="font-medium text-ink">synthetic</strong> bakery sales.
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <Button busy={importing} onClick={loadSample} icon={<Database className="size-4" />}>
                  Load synthetic sample sales
                </Button>
                <Link href="/orders">
                  <Button variant="secondary">Upload my own CSV</Button>
                </Link>
              </div>
              {importError && <div className="mt-3"><ErrorState message={importError} /></div>}
            </div>
            <ol className="space-y-2 text-sm">
              {steps.map((s, i) => (
                <li key={s.label} className="flex items-center gap-3 rounded-lg border border-line bg-cream px-3 py-2.5">
                  <span className="flex size-6 items-center justify-center rounded-full bg-forest-50 text-xs font-semibold text-forest">{i + 1}</span>
                  {s.label}
                </li>
              ))}
            </ol>
          </div>
        </Card>
      )}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Orders today" value={todays.reduce((s, o) => s + o.quantity, 0)} hint={`${todays.length} order lines`} loading={orders.loading} />
        <Stat label="Upcoming pre-orders" value={preorders.reduce((s, o) => s + o.quantity, 0)} hint="units promised to customers" loading={orders.loading} />
        <Stat
          label="Expected demand"
          value={expected !== undefined && upcoming?.target_date ? num(expected, 0) : "—"}
          hint={upcoming?.target_date ? `units for ${formatDay(upcoming.target_date)} · ${upcoming.model_label}` : "generate a plan or run a forecast"}
          loading={forecast.loading}
        />
        <Stat label="Awaiting approval" value={pending.length} hint={pending.length ? "plan needs your review" : "nothing pending"} loading={plans.loading} />
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Card
          title="Kitchen plan"
          description={latestPlan ? `For ${formatLongDay(latestPlan.target_date)}` : "Nothing planned yet"}
          actions={latestPlan && <Badge tone={PLAN_TONE[latestPlan.status]}>{latestPlan.status}</Badge>}
        >
          {plans.loading ? (
            <Loading />
          ) : plans.error ? (
            <ErrorState message={plans.error} onRetry={plans.reload} />
          ) : !latestPlan ? (
            <Empty title="No plan yet" icon={<ChefHat className="size-5" />} action={hasHistory && <Link href="/plan"><Button variant="secondary">Generate a plan</Button></Link>}>
              {hasHistory ? "Your history is ready. Generate tomorrow's plan to see what to bake." : "Load sales history first, then generate a plan."}
            </Empty>
          ) : (
            <>
              <ul className="divide-y divide-line">
                {latestPlan.items.filter((i) => i.final_quantity > 0).map((i) => (
                  <li key={i.product_id} className="flex items-center justify-between py-2.5 text-sm">
                    <span>{i.product_name}</span>
                    <span className="tabular font-medium text-forest">{i.final_quantity}</span>
                  </li>
                ))}
              </ul>
              <Link href="/plan" className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-forest hover:underline">
                {latestPlan.status === "approved" ? "View approved plan" : "Review and approve"} <ArrowRight className="size-4" />
              </Link>
            </>
          )}
        </Card>

        <Card title="Things to watch" description="From the latest plan">
          {plans.loading ? (
            <Loading />
          ) : !latestPlan || latestPlan.warnings.length === 0 ? (
            <p className="text-sm text-muted">{latestPlan ? "No alerts for this plan." : "Alerts appear once a plan is generated."}</p>
          ) : (
            <ul className="space-y-2">
              {latestPlan.warnings.slice(0, 5).map((w, i) => (
                <li key={i}>
                  <Notice tone={w.severity === "warning" ? "amber" : "neutral"} icon={<AlertTriangle className="size-4" />}>
                    {w.message}
                  </Notice>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card className="mt-6" title="Recent activity" description="Latest orders saved" padded={false}>
        {orders.loading ? (
          <Loading className="px-5" />
        ) : orders.error ? (
          <div className="p-5"><ErrorState message={orders.error} onRetry={orders.reload} /></div>
        ) : recent.length === 0 ? (
          <Empty title="No orders yet" icon={<ReceiptText className="size-5" />} />
        ) : (
          <ul className="divide-y divide-line">
            {recent.map((o) => (
              <li key={o.id} className="flex flex-wrap items-center justify-between gap-2 px-5 py-3 text-sm">
                <span className="min-w-0">
                  <span className="font-medium">{o.quantity} × {o.product_name}</span>
                  {o.customer_name && <span className="text-muted"> for {o.customer_name}</span>}
                  <span className="text-muted"> · {formatDay(o.order_date)}</span>
                </span>
                <span className="flex items-center gap-2 text-xs text-muted">
                  <Badge tone={o.source === "message" ? "sage" : "neutral"}>{SOURCE_LABEL[o.source]}</Badge>
                  {formatTimestamp(o.created_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <div className={cx("mt-6 grid gap-3 sm:grid-cols-4", !hasHistory && "hidden")}>
        {steps.map((s) => (
          <Link key={s.label} href={s.href} className="flex items-center gap-2 rounded-lg border border-line bg-paper px-3 py-2.5 text-sm hover:border-forest/30">
            <span className={cx("flex size-5 items-center justify-center rounded-full", s.done ? "bg-forest text-cream" : "border border-line-strong text-transparent")}>
              <Check className="size-3" />
            </span>
            <span className={s.done ? "text-muted line-through decoration-line-strong" : "text-ink"}>{s.label}</span>
          </Link>
        ))}
      </div>
    </>
  );
}
