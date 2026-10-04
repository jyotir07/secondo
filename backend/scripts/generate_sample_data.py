"""Generate the SYNTHETIC bakery sales history used for demos and tests.

Deterministic (fixed seed). Patterns modelled: closed on Mondays, weekend peaks, a gentle
upward trend, a post-payday bump in the first days of each month, and occasional cookie
promotions. None of this is real sales data.

Usage: uv run python scripts/generate_sample_data.py
"""

import csv
from datetime import date, timedelta

import numpy as np

from app.config import SAMPLE_SALES_CSV
from app.seed import STARTER_PRODUCTS

SEED = 42
START = date(2026, 6, 2)
END = date(2026, 10, 3)

BASE_DAILY = {
    "sourdough-loaf": 12,
    "butter-croissant": 26,
    "chocolate-chip-cookie": 34,
    "cinnamon-roll": 15,
    "banana-bread": 5,
    "chocolate-cake-1kg": 1.2,
}
# Monday = 0. Monday is a closed day, so it never appears.
WEEKDAY_FACTOR = {1: 0.8, 2: 0.85, 3: 0.95, 4: 1.1, 5: 1.5, 6: 1.35}


def main() -> None:
    rng = np.random.default_rng(SEED)
    total_days = (END - START).days
    rows = []
    day = START
    while day <= END:
        if day.weekday() in WEEKDAY_FACTOR:
            trend = 1 + 0.12 * (day - START).days / total_days
            payday = 1.1 if day.day <= 5 else 1.0
            for spec in STARTER_PRODUCTS:
                pid = spec["id"]
                promotion = pid == "chocolate-chip-cookie" and rng.random() < 0.08
                lam = BASE_DAILY[pid] * WEEKDAY_FACTOR[day.weekday()] * trend * payday
                if promotion:
                    lam *= 1.4
                qty = int(rng.poisson(lam))
                if qty == 0:
                    continue
                rows.append(
                    {
                        "date": day.isoformat(),
                        "weekday": day.strftime("%A"),
                        "product_id": pid,
                        "product_name": spec["name"],
                        "quantity_sold": qty,
                        "price": spec["selling_price"],
                        "promotion": int(promotion),
                    }
                )
        day += timedelta(days=1)

    SAMPLE_SALES_CSV.parent.mkdir(parents=True, exist_ok=True)
    with SAMPLE_SALES_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} synthetic rows ({START} to {END}) to {SAMPLE_SALES_CSV}")


if __name__ == "__main__":
    main()
