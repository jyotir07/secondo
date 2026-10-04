export type OrderStatus = "pending" | "confirmed" | "completed" | "cancelled";
export type OrderSource = "csv_import" | "manual" | "message";
export type PlanStatus = "draft" | "approved" | "rejected" | "modified";

export interface Business {
  id: string;
  name: string;
  business_type: string;
  timezone: string;
  currency: string;
}

export interface Product {
  id: string;
  name: string;
  category: string;
  selling_price: number;
  active: boolean;
}

export interface OrderView {
  id: string;
  order_date: string;
  product_id: string;
  product_name: string;
  quantity: number;
  customer_name: string | null;
  status: OrderStatus;
  source: OrderSource;
  notes: string | null;
  original_input: string | null;
  extraction_confidence: number | null;
  created_at: string;
}

export interface OrderList {
  total: number;
  orders: OrderView[];
}

export interface ImportResult {
  total_rows: number;
  imported: number;
  duplicates: number;
  skipped_zero_quantity: number;
  errors: { line: number; message: string }[];
  first_date: string | null;
  last_date: string | null;
}

export interface ExtractedItem {
  product_id: string | null;
  product_name: string;
  mention: string;
  quantity: number;
  matched: boolean;
}

export interface ExtractionResult {
  items: ExtractedItem[];
  order_date: string | null;
  customer_name: string | null;
  dietary_constraints: string[];
  notes: string | null;
  confidence: number;
  provider: string;
  model: string | null;
  fallback_used: boolean;
  fallback_reason: string | null;
  warnings: string[];
  original_input: string;
  latency_ms: number | null;
}

export interface OrderCreate {
  order_date: string;
  items: { product_id: string; quantity: number }[];
  customer_name?: string | null;
  dietary_constraints?: string[];
  notes?: string | null;
  source?: OrderSource;
  original_input?: string | null;
  extraction_confidence?: number | null;
  allow_duplicate?: boolean;
}

export interface OrderCreateResult {
  created: OrderView[];
  duplicates: number;
}

export interface Forecast {
  id: string;
  product_id: string;
  target_date: string;
  predicted_quantity: number;
  model_name: string;
  baseline_quantity: number;
  evaluation_metadata: {
    backtest_mae?: number | null;
    backtest_days?: number;
    fallback_reason?: string | null;
    [key: string]: unknown;
  };
  created_at: string;
}

export interface ForecastResponse {
  target_date: string | null;
  model_name: string;
  model_label: string;
  baseline_name: string;
  forecasts: Forecast[];
  history: { date: string; product_id: string; quantity: number }[];
}

export interface ProviderMetrics {
  provider: string;
  label: string;
  mae: number;
  wape: number | null;
  bias: number;
  by_product: Record<string, { product_id: string; mae: number; wape: number | null; bias: number; n: number }>;
}

export interface EvaluationReport {
  method: string;
  history_start: string | null;
  history_end: string | null;
  open_days: number;
  observations: number;
  holdout_start: string | null;
  holdout_end: string | null;
  holdout_days: number;
  metrics: ProviderMetrics[];
  points: { date: string; product_id: string; actual: number; predictions: Record<string, number> }[];
  sufficient_data: boolean;
  notes: string[];
}

export interface KitchenPlanItem {
  product_id: string;
  product_name: string;
  predicted_quantity: number;
  baseline_quantity: number;
  typical_error: number | null;
  confirmed_quantity: number;
  recommended_quantity: number;
  final_quantity: number;
  explanation: string;
}

export interface KitchenPlan {
  id: string;
  target_date: string;
  items: KitchenPlanItem[];
  explanations: string[];
  warnings: { severity: "info" | "warning"; message: string; product_id: string | null }[];
  ingredient_needs: { ingredient: string; unit: string; quantity: number }[];
  customer_requests: {
    order_id: string;
    customer_name: string | null;
    product_name: string;
    quantity: number;
    dietary_constraints: string[];
    notes: string | null;
  }[];
  model_name: string;
  status: PlanStatus;
  review_note: string | null;
  approved_at: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface ProviderStatus {
  mode: string;
  extraction: {
    configured: string;
    active: string;
    model: string | null;
    available: boolean;
    detail: string;
    [key: string]: unknown;
  };
  forecasting: {
    configured: string;
    active: string;
    active_label: string;
    baseline: string;
    fallback_reason: string | null;
    available: { name: string; label: string; description: string }[];
    [key: string]: unknown;
  };
  database: { backend: string; location: string };
  business: { timezone: string; today: string };
}

export interface Health {
  status: string;
  database: string;
  today: string;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

function describe(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // FastAPI validation errors: [{loc, msg}]
    return detail
      .map((d) => {
        const loc = Array.isArray(d?.loc) ? d.loc.filter((p: unknown) => p !== "body").join(".") : "";
        return loc ? `${loc}: ${d?.msg}` : String(d?.msg ?? d);
      })
      .join("; ");
  }
  return "Unexpected response from the server.";
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, {
      ...init,
      headers:
        init?.body && !(init.body instanceof FormData)
          ? { "Content-Type": "application/json", ...init?.headers }
          : init?.headers,
      cache: "no-store",
    });
  } catch {
    throw new ApiError("Can't reach the SECONDO server. Is the backend running?", 0);
  }
  if (!res.ok) {
    let message = `Request failed (${res.status}).`;
    try {
      const body = await res.json();
      if (body?.detail) message = describe(body.detail);
    } catch {
      if (res.status >= 500) message = "The SECONDO server is unavailable or hit an error.";
    }
    throw new ApiError(message, res.status);
  }
  return res.json() as Promise<T>;
}

export const post = <T>(path: string, body: unknown = {}) =>
  api<T>(path, { method: "POST", body: JSON.stringify(body) });
