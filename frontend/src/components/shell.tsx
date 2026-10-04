"use client";

import { ChefHat, LayoutDashboard, LineChart, ReceiptText, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import type { Business, ProviderStatus } from "@/lib/api";
import { PROVIDER_LABEL } from "@/lib/format";
import { useApi } from "@/lib/use-api";
import { cx } from "./ui";

const NAV = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/orders", label: "Orders", icon: ReceiptText },
  { href: "/forecast", label: "Forecast", icon: LineChart },
  { href: "/plan", label: "Kitchen Plan", icon: ChefHat },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const business = useApi<Business>("/business");
  const providers = useApi<ProviderStatus>("/settings/providers");
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <div className="flex min-h-dvh flex-col lg:flex-row">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-line bg-paper/60 px-4 py-6 lg:flex lg:sticky lg:top-0 lg:h-dvh">
        <Link href="/" className="px-2">
          <span className="font-serif text-2xl tracking-tight text-forest">Secondo</span>
          <span className="mt-0.5 block text-xs text-muted">{business.data?.name ?? " "}</span>
        </Link>
        <nav className="mt-8 flex flex-col gap-0.5" aria-label="Primary">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              aria-current={isActive(href) ? "page" : undefined}
              className={cx(
                "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors",
                isActive(href) ? "bg-forest text-cream" : "text-ink/80 hover:bg-forest-50 hover:text-forest",
              )}
            >
              <Icon className="size-4" aria-hidden /> {label}
            </Link>
          ))}
        </nav>
        <div className="mt-auto rounded-lg border border-line bg-cream px-3 py-3 text-xs text-muted">
          <p className="font-medium text-ink">Runs on this computer</p>
          {providers.data ? (
            <p className="mt-1 leading-relaxed">
              Orders read by {PROVIDER_LABEL[providers.data.extraction.active] ?? providers.data.extraction.active}.
              Forecasts by {providers.data.forecasting.active_label}.
            </p>
          ) : providers.error ? (
            <p className="mt-1 text-danger">Server offline</p>
          ) : (
            <p className="mt-1">Checking…</p>
          )}
        </div>
      </aside>

      <header className="sticky top-0 z-20 border-b border-line bg-cream/95 backdrop-blur lg:hidden">
        <div className="flex items-baseline justify-between px-4 pt-3">
          <span className="font-serif text-xl text-forest">Secondo</span>
          <span className="truncate pl-4 text-xs text-muted">{business.data?.name}</span>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-3 py-2 [scrollbar-width:none]" aria-label="Primary">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              aria-current={isActive(href) ? "page" : undefined}
              className={cx(
                "flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-sm",
                isActive(href) ? "bg-forest text-cream" : "text-ink/80 hover:bg-forest-50",
              )}
            >
              <Icon className="size-3.5" aria-hidden /> {label}
            </Link>
          ))}
        </nav>
      </header>

      <main className="min-w-0 flex-1 px-4 py-8 sm:px-8 lg:px-12 lg:py-10">
        <div className="mx-auto max-w-6xl">{children}</div>
      </main>
    </div>
  );
}
