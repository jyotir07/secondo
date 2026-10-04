import { AlertTriangle, Inbox, Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

export function PageHeader({ eyebrow, title, description, actions }: {
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="max-w-2xl">
        {eyebrow && <p className="mb-2 text-xs font-medium uppercase tracking-[0.14em] text-sage">{eyebrow}</p>}
        <h1 className="font-serif text-3xl leading-tight text-forest sm:text-4xl">{title}</h1>
        {description && <p className="mt-2 text-[15px] leading-relaxed text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function Card({ title, description, actions, children, className, padded = true }: {
  title?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return (
    <section className={cx("rounded-xl border border-line bg-paper shadow-card", className)}>
      {(title || actions) && (
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div>
            {title && <h2 className="text-[15px] font-semibold text-ink">{title}</h2>}
            {description && <p className="mt-0.5 text-sm text-muted">{description}</p>}
          </div>
          {actions}
        </div>
      )}
      <div className={padded ? "p-5" : undefined}>{children}</div>
    </section>
  );
}

type Variant = "primary" | "secondary" | "ghost" | "danger";
const VARIANTS: Record<Variant, string> = {
  primary: "bg-forest text-cream hover:bg-forest-600 border border-forest",
  secondary: "bg-paper text-ink border border-line-strong hover:bg-cream",
  ghost: "text-forest hover:bg-forest-50 border border-transparent",
  danger: "bg-paper text-danger border border-danger/40 hover:bg-danger-50",
};

export function Button({ variant = "primary", busy, icon, children, className, disabled, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; busy?: boolean; icon?: ReactNode }) {
  return (
    <button
      {...rest}
      disabled={disabled || busy}
      className={cx(
        "inline-flex h-9 items-center justify-center gap-2 rounded-lg px-3.5 text-sm font-medium transition-colors",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forest",
        "disabled:cursor-not-allowed disabled:opacity-50",
        VARIANTS[variant],
        className,
      )}
    >
      {busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
}

type Tone = "neutral" | "green" | "amber" | "red" | "sage";
const TONES: Record<Tone, string> = {
  neutral: "bg-cream text-muted border-line",
  green: "bg-forest-50 text-forest border-forest/15",
  sage: "bg-sage-100 text-forest-600 border-sage/30",
  amber: "bg-amber-50 text-amber border-amber/20",
  red: "bg-danger-50 text-danger border-danger/20",
};

export function Badge({ tone = "neutral", children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-xs font-medium", TONES[tone], className)}>
      {children}
    </span>
  );
}

export function Loading({ label = "Loading…", className }: { label?: string; className?: string }) {
  return (
    <div role="status" className={cx("flex items-center gap-2 py-8 text-sm text-muted", className)}>
      <Loader2 className="size-4 animate-spin" aria-hidden /> {label}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("animate-pulse rounded-md bg-line/60", className)} />;
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-start gap-3 rounded-lg border border-danger/20 bg-danger-50 p-4 text-sm text-danger sm:flex-row sm:items-center sm:justify-between">
      <span className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden /> {message}
      </span>
      {onRetry && <Button variant="danger" onClick={onRetry}>Try again</Button>}
    </div>
  );
}

export function Notice({ tone = "amber", children, icon }: { tone?: "amber" | "green" | "neutral"; children: ReactNode; icon?: ReactNode }) {
  const styles = {
    amber: "border-amber/20 bg-amber-50 text-amber",
    green: "border-forest/15 bg-forest-50 text-forest",
    neutral: "border-line bg-cream text-muted",
  }[tone];
  return (
    <div className={cx("flex items-start gap-2 rounded-lg border px-3.5 py-2.5 text-sm", styles)}>
      {icon && <span className="mt-0.5 shrink-0">{icon}</span>}
      <div className="min-w-0">{children}</div>
    </div>
  );
}

export function Empty({ title, children, action, icon }: { title: string; children?: ReactNode; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center px-4 py-10 text-center">
      <div className="mb-3 flex size-10 items-center justify-center rounded-full bg-forest-50 text-forest">
        {icon ?? <Inbox className="size-5" aria-hidden />}
      </div>
      <p className="font-medium text-ink">{title}</p>
      {children && <p className="mt-1 max-w-sm text-sm text-muted">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Stat({ label, value, hint, loading }: { label: string; value: ReactNode; hint?: ReactNode; loading?: boolean }) {
  return (
    <div className="rounded-xl border border-line bg-paper p-5 shadow-card">
      <p className="text-xs font-medium uppercase tracking-[0.12em] text-muted">{label}</p>
      {loading ? <Skeleton className="mt-3 h-8 w-20" /> : <p className="tabular mt-2 font-serif text-3xl text-forest">{value}</p>}
      {hint && <p className="mt-1 text-sm text-muted">{hint}</p>}
    </div>
  );
}

export const inputClass =
  "h-9 w-full rounded-lg border border-line-strong bg-paper px-3 text-sm text-ink placeholder:text-muted/70 " +
  "focus:border-forest focus:outline-none focus:ring-2 focus:ring-forest/15 disabled:opacity-60";

export function Field({ label, htmlFor, children, hint }: { label: string; htmlFor?: string; children: ReactNode; hint?: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-xs font-medium text-muted">{label}</label>
      {children}
      {hint && <p className="text-xs text-muted">{hint}</p>}
    </div>
  );
}
