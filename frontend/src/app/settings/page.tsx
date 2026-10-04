"use client";

import { Cpu, Database, Download, LineChart, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { Badge, Card, ErrorState, Loading, Notice, PageHeader } from "@/components/ui";
import type { Business, ProviderStatus } from "@/lib/api";
import { PROVIDER_LABEL } from "@/lib/format";
import { useApi } from "@/lib/use-api";

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 py-2.5 text-sm sm:flex-row sm:justify-between sm:gap-6">
      <dt className="text-muted">{label}</dt>
      <dd className="break-all text-left sm:text-right">{children}</dd>
    </div>
  );
}

export default function SettingsPage() {
  const status = useApi<ProviderStatus>("/settings/providers");
  const business = useApi<Business>("/business");
  const s = status.data;

  return (
    <>
      <PageHeader
        eyebrow="Settings"
        title="Where your data goes"
        description="Which models are reading your orders and forecasting demand, and where everything is stored."
      />
      {status.loading && !s ? (
        <Loading />
      ) : status.error ? (
        <ErrorState message={status.error} onRetry={status.reload} />
      ) : s && (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card title="Order reading" actions={<Cpu className="size-5 text-sage" aria-hidden />}>
            <dl className="divide-y divide-line">
              <Row label="Active">
                <Badge tone={s.extraction.active === "rules" ? "neutral" : "green"}>{PROVIDER_LABEL[s.extraction.active] ?? s.extraction.active}</Badge>
              </Row>
              <Row label="Configured">{s.extraction.configured}</Row>
              {s.extraction.model && <Row label="Model">{s.extraction.model}</Row>}
            </dl>
            <p className="mt-3 text-sm text-muted">{s.extraction.detail}</p>
          </Card>

          <Card title="Forecasting" actions={<LineChart className="size-5 text-sage" aria-hidden />}>
            <dl className="divide-y divide-line">
              <Row label="Active"><Badge tone="green">{s.forecasting.active_label}</Badge></Row>
              <Row label="Configured">{s.forecasting.configured}</Row>
              <Row label="Compared against">{PROVIDER_LABEL[s.forecasting.baseline] ?? s.forecasting.baseline}</Row>
            </dl>
            {s.forecasting.fallback_reason && <div className="mt-3"><Notice>{s.forecasting.fallback_reason}</Notice></div>}
            <ul className="mt-3 space-y-1.5 text-sm text-muted">
              {s.forecasting.available.map((p) => (
                <li key={p.name}><span className="font-medium text-ink">{p.label}:</span> {p.description}</li>
              ))}
            </ul>
          </Card>

          <Card title="Storage" actions={<Database className="size-5 text-sage" aria-hidden />}>
            <dl className="divide-y divide-line">
              <Row label="Database"><Badge>{s.database.backend}</Badge></Row>
              <Row label="Location"><code className="text-xs">{s.database.location}</code></Row>
              <Row label="Business">{business.data?.name}</Row>
              <Row label="Timezone">{s.business.timezone}</Row>
              <Row label="Currency">{business.data?.currency}</Row>
              <Row label="Sales history">
                {business.data?.sample_data_loaded ? <Badge tone="amber">Includes synthetic sample data</Badge> : "Your own data"}
              </Row>
            </dl>
            <div className="mt-4 flex flex-wrap gap-2">
              <a href="/api/export" download className="inline-flex h-9 items-center gap-2 rounded-lg border border-forest bg-forest px-3.5 text-sm font-medium text-cream hover:bg-forest-600">
                <Download className="size-4" aria-hidden /> Export all my data (JSON)
              </a>
              <a href="/api/orders/sample-csv" download className="inline-flex h-9 items-center gap-2 rounded-lg border border-line-strong bg-paper px-3.5 text-sm font-medium text-ink hover:bg-cream">
                CSV template (sample)
              </a>
            </div>
          </Card>

          <Card title="Privacy" actions={<ShieldCheck className="size-5 text-sage" aria-hidden />}>
            <div className="space-y-3 text-sm leading-relaxed text-muted">
              <p>
                <strong className="font-medium text-ink">Local mode (this setup).</strong> Orders, customer names and sales history
                stay in the database file above. Messages are read on this machine; no cloud AI service receives them.
              </p>
              <p>
                <strong className="font-medium text-ink">Hosted demo.</strong> A hosted deployment stores data on that server and is not
                offline. Use it with sample data, not real customer details.
              </p>
            </div>
          </Card>
        </div>
      )}
    </>
  );
}
