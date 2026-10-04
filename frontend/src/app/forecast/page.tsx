"use client";

import { FlaskConical, LineChart as LineIcon, Play } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Badge, Button, Card, Empty, ErrorState, Loading, Notice, PageHeader, cx, inputClass } from "@/components/ui";
import { post, type EvaluationReport, type ForecastResponse, type Product } from "@/lib/api";
import { PROVIDER_LABEL, formatDay, formatShortDay, num } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const C = { actual: "#8a8170", model: "#1f3d2b", baseline: "#8fa98f", grid: "#e7e1d3", axis: "#66705f", amber: "#b45309" };
const axisProps = { stroke: C.axis, fontSize: 12, tickLine: false, axisLine: false } as const;
const tooltipStyle = { borderRadius: 8, border: `1px solid ${C.grid}`, fontSize: 13, background: "#fffdf8" };

export default function ForecastPage() {
  const products = useApi<Product[]>("/products");
  const forecast = useApi<ForecastResponse>("/forecasts?history_days=56");
  const evaluation = useApi<EvaluationReport>("/forecasts/evaluation");
  const [selected, setSelected] = useState("");
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string>();

  const productList = (products.data ?? []).filter((p) => p.active);
  const pid = selected || productList[0]?.id || "";
  const productName = productList.find((p) => p.id === pid)?.name ?? "";
  const fc = forecast.data?.forecasts.find((f) => f.product_id === pid);
  const hasHistory = (forecast.data?.history.length ?? 0) > 0;

  async function run() {
    setRunning(true);
    setRunError(undefined);
    try {
      await post<ForecastResponse>("/forecasts/run", {});
      await Promise.all([forecast.reload(), evaluation.reload()]);
    } catch (e) {
      setRunError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  const historyData = (forecast.data?.history ?? [])
    .filter((h) => h.product_id === pid)
    .map((h) => ({ date: h.date, actual: h.quantity }));
  const chartData: { date: string; actual?: number; forecast?: number; baseline?: number }[] = [...historyData];
  if (fc) chartData.push({ date: fc.target_date, forecast: fc.predicted_quantity, baseline: fc.baseline_quantity });

  const ev = evaluation.data;
  const providers = ev?.metrics ?? [];
  const backtestData = (ev?.points ?? [])
    .filter((p) => p.product_id === pid)
    .map((p) => ({ date: p.date, actual: p.actual, ...p.predictions }));
  const seriesColor = (name: string) =>
    name === forecast.data?.baseline_name ? C.baseline : name === forecast.data?.model_name ? C.model : C.amber;
  const best = providers.length > 1 ? [...providers].sort((a, b) => a.mae - b.mae)[0] : undefined;

  return (
    <>
      <PageHeader
        eyebrow="Predict"
        title="Demand forecast"
        description="How many of each item you're likely to sell, checked against what actually happened in recent weeks."
        actions={
          <Button onClick={run} busy={running} disabled={!hasHistory && !forecast.loading} icon={<Play className="size-4" />}>
            {forecast.data?.target_date ? "Re-run forecast" : "Run forecast"}
          </Button>
        }
      />

      {runError && <div className="mb-6"><ErrorState message={runError} /></div>}
      {forecast.error && <div className="mb-6"><ErrorState message={forecast.error} onRetry={forecast.reload} /></div>}

      {forecast.loading && !forecast.data ? (
        <Loading />
      ) : !hasHistory ? (
        <Card>
          <Empty title="No sales history yet" icon={<LineIcon className="size-5" />} action={<Link href="/orders"><Button variant="secondary">Import sales</Button></Link>}>
            Forecasts are learned from your own past sales. Import a CSV on the Orders page to begin.
          </Empty>
        </Card>
      ) : (
        <>
          <div className="mb-6 flex flex-wrap items-center gap-x-3 gap-y-2">
            <label htmlFor="product" className="text-sm text-muted">Product</label>
            <select id="product" value={pid} onChange={(e) => setSelected(e.target.value)} className={cx(inputClass, "sm:w-64")}>
              {productList.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            <Badge tone="green">Model: {forecast.data?.model_label}</Badge>
            <Badge>Baseline: {PROVIDER_LABEL[forecast.data?.baseline_name ?? ""] ?? forecast.data?.baseline_name}</Badge>
          </div>

          <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
            <Card title={`${productName}: last 8 weeks`} description={fc ? `Forecast for ${formatDay(fc.target_date)} shown at the right edge` : "Run a forecast to add the next day"}>
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
                    <CartesianGrid stroke={C.grid} vertical={false} />
                    <XAxis dataKey="date" tickFormatter={formatShortDay} minTickGap={28} {...axisProps} />
                    <YAxis allowDecimals={false} {...axisProps} />
                    <Tooltip contentStyle={tooltipStyle} labelFormatter={(d) => formatDay(String(d))} formatter={(v) => num(Number(v))} />
                    <Legend wrapperStyle={{ fontSize: 12 }} iconType="plainline" />
                    {fc && <ReferenceLine x={fc.target_date} stroke={C.grid} strokeDasharray="4 4" />}
                    <Line name="Sold" dataKey="actual" stroke={C.actual} strokeWidth={1.5} dot={false} connectNulls={false} isAnimationActive={false} />
                    <Line name={forecast.data?.model_label ?? "Forecast"} dataKey="forecast" stroke={C.model} strokeWidth={0} dot={{ r: 5, fill: C.model }} isAnimationActive={false} />
                    <Line name="Baseline" dataKey="baseline" stroke={C.baseline} strokeWidth={0} dot={{ r: 5, fill: C.baseline }} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Card>

            <Card title="Next forecast">
              {!fc ? (
                <p className="text-sm text-muted">No forecast saved yet. Press <strong>Run forecast</strong>.</p>
              ) : (
                <dl className="space-y-4">
                  <div>
                    <dt className="text-xs uppercase tracking-wide text-muted">{formatDay(fc.target_date)}</dt>
                    <dd className="tabular font-serif text-4xl text-forest">{num(fc.predicted_quantity)}</dd>
                    <dd className="text-sm text-muted">expected units · {forecast.data?.model_label}</dd>
                  </div>
                  <div className="border-t border-line pt-3 text-sm">
                    <dt className="text-muted">Baseline says</dt>
                    <dd className="tabular font-medium">{num(fc.baseline_quantity)}</dd>
                  </div>
                  {fc.evaluation_metadata.backtest_mae != null && (
                    <div className="border-t border-line pt-3 text-sm">
                      <dt className="text-muted">Typical miss (MAE, last {fc.evaluation_metadata.backtest_days} days)</dt>
                      <dd className="tabular font-medium">± {num(fc.evaluation_metadata.backtest_mae)} units</dd>
                    </div>
                  )}
                  {fc.evaluation_metadata.fallback_reason && <Notice>{fc.evaluation_metadata.fallback_reason}</Notice>}
                </dl>
              )}
            </Card>
          </div>

          <Card
            className="mt-6"
            title="How accurate has this been?"
            description={ev?.sufficient_data ? `Backtest on ${ev.holdout_days} open days, ${formatShortDay(ev.holdout_start!)} – ${formatShortDay(ev.holdout_end!)}` : undefined}
            actions={<FlaskConical className="size-5 text-sage" aria-hidden />}
          >
            {evaluation.loading && !ev ? (
              <Loading />
            ) : evaluation.error ? (
              <ErrorState message={evaluation.error} onRetry={evaluation.reload} />
            ) : !ev?.sufficient_data ? (
              <Notice>{ev?.notes.join(" ") ?? "Not enough data to evaluate yet."}</Notice>
            ) : (
              <div className="grid gap-6 lg:grid-cols-[1fr_1.3fr]">
                <div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
                          <th className="py-2 font-medium">Method</th>
                          <th className="py-2 pl-4 text-right font-medium" title="Mean absolute error, units per product per day">MAE</th>
                          <th className="py-2 pl-4 text-right font-medium" title="Weighted absolute percentage error">WAPE</th>
                          <th className="py-2 pl-4 text-right font-medium" title="Average over (+) or under (−) prediction">Bias</th>
                          <th className="py-2 pl-4 text-right font-medium">{productName} MAE</th>
                        </tr>
                      </thead>
                      <tbody className="tabular divide-y divide-line">
                        {providers.map((m) => (
                          <tr key={m.provider}>
                            <td className="py-2.5">
                              {m.label}
                              {best?.provider === m.provider && <Badge tone="green" className="ml-2">lowest error</Badge>}
                            </td>
                            <td className="py-2.5 pl-4 text-right font-medium">{num(m.mae, 2)}</td>
                            <td className="py-2.5 pl-4 text-right">{m.wape != null ? `${num(m.wape * 100)}%` : "—"}</td>
                            <td className="py-2.5 pl-4 text-right">{m.bias > 0 ? "+" : ""}{num(m.bias, 2)}</td>
                            <td className="py-2.5 pl-4 text-right">{m.by_product[pid] ? num(m.by_product[pid].mae, 2) : "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="mt-4 space-y-2 text-sm leading-relaxed text-muted">
                    <p>{ev.method}</p>
                    <p>
                      Data: {ev.open_days} open days ({formatShortDay(ev.history_start!)} – {formatShortDay(ev.history_end!)}), {ev.observations} product-day observations.
                    </p>
                    {ev.notes.map((n) => <p key={n}>{n}</p>)}
                  </div>
                </div>
                <div>
                  <p className="mb-2 text-sm font-medium">{productName}: actual vs predicted</p>
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={backtestData} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
                        <CartesianGrid stroke={C.grid} vertical={false} />
                        <XAxis dataKey="date" tickFormatter={formatShortDay} minTickGap={24} {...axisProps} />
                        <YAxis allowDecimals={false} {...axisProps} />
                        <Tooltip contentStyle={tooltipStyle} labelFormatter={(d) => formatDay(String(d))} formatter={(v) => num(Number(v))} />
                        <Legend wrapperStyle={{ fontSize: 12 }} iconType="plainline" />
                        <Line name="Actual" dataKey="actual" stroke={C.actual} strokeWidth={2} dot={{ r: 2.5 }} isAnimationActive={false} />
                        {[...providers].reverse().map((m) => (
                          <Line
                            key={m.provider}
                            name={m.label}
                            dataKey={m.provider}
                            stroke={seriesColor(m.provider)}
                            strokeDasharray={m.provider === forecast.data?.baseline_name ? "5 4" : undefined}
                            strokeWidth={2}
                            dot={false}
                            isAnimationActive={false}
                          />
                        ))}
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>
            )}
          </Card>
        </>
      )}
    </>
  );
}
