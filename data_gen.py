"""Generate simulated logistics sales data and store it in SQLite.

Every figure produced here is synthetic. It exists to demonstrate analysis and
dashboarding. It is not DHL company performance, and customer names are
placeholders ("Account 001").
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 20260101
FIRST_MONTH = "2024-01"
LAST_MONTH = "2026-10"          # last month of actuals
FORECAST_END = "2027-04"        # targets are generated through this month
N_CUSTOMERS = 300
MONTHLY_GROWTH = 0.006
SEASONALITY = [0.90, 0.85, 0.95, 1.00, 1.02, 1.05, 1.00, 0.95, 1.03, 1.06, 1.12, 1.20]
BANNER = "SIMULATED DATA. Generated for demonstration only. Not DHL company performance."

# country, ISO-3, region, relative market size
COUNTRIES = [
    ("United Kingdom", "GBR", "EMEA", 1.00),
    ("Germany", "DEU", "EMEA", 0.90),
    ("France", "FRA", "EMEA", 0.70),
    ("Netherlands", "NLD", "EMEA", 0.40),
    ("United Arab Emirates", "ARE", "EMEA", 0.50),
    ("India", "IND", "APAC", 0.80),
    ("Singapore", "SGP", "APAC", 0.45),
    ("Japan", "JPN", "APAC", 0.60),
    ("Australia", "AUS", "APAC", 0.55),
    ("United States", "USA", "Americas", 1.20),
    ("Canada", "CAN", "Americas", 0.50),
    ("Brazil", "BRA", "Americas", 0.45),
    ("Mexico", "MEX", "Americas", 0.35),
]

# service: (category, list price per shipment, typical shipments per month at SME scale)
SERVICES = {
    "Express Domestic": ("Express", 38.0, 26),
    "Express International": ("Express", 118.0, 14),
    "E-commerce Parcel": ("E-commerce", 19.0, 60),
    "Road Freight": ("Freight", 360.0, 4),
    "Air Freight": ("Freight", 880.0, 2.5),
    "Ocean Freight": ("Freight", 1350.0, 1.5),
}

# segment: (share of customers, volume scale, price discount)
SEGMENTS = {
    "Enterprise": (0.08, 9.0, 0.85),
    "Mid-Market": (0.27, 2.8, 0.95),
    "SME": (0.65, 1.0, 1.00),
}
SEGMENT_SERVICE_COUNT = {"Enterprise": 4, "Mid-Market": 2, "SME": 1}

SCHEMA_EXTRAS = """
CREATE INDEX IF NOT EXISTS idx_shipments_month ON shipments(month);
CREATE INDEX IF NOT EXISTS idx_shipments_customer ON shipments(customer_id);
CREATE INDEX IF NOT EXISTS idx_targets_month ON targets(month, region);
CREATE VIEW IF NOT EXISTS fact_sales AS
SELECT s.month, s.customer_id, c.customer_name, c.country, c.iso3, c.region, c.segment,
       s.service, sv.category, s.shipments, s.revenue
FROM shipments s
JOIN customers c ON c.customer_id = s.customer_id
JOIN services sv ON sv.service_name = s.service;
"""


def _periods(start: str, end: str) -> pd.PeriodIndex:
    return pd.period_range(start, end, freq="M")


def generate(seed: int = SEED) -> dict[str, pd.DataFrame]:
    """Return the simulated tables as DataFrames, deterministically for a given seed."""
    rng = np.random.default_rng(seed)
    months = _periods(FIRST_MONTH, LAST_MONTH)
    countries = pd.DataFrame(COUNTRIES, columns=["country", "iso3", "region", "market_size"])
    country_p = (countries["market_size"] / countries["market_size"].sum()).to_numpy()
    seg_names = list(SEGMENTS)
    seg_p = np.array([SEGMENTS[s][0] for s in seg_names])
    svc_names = list(SERVICES)

    # Customers: some onboard after the start, some churn, some decline or grow.
    customers = []
    for i in range(N_CUSTOMERS):
        c = countries.iloc[rng.choice(len(countries), p=country_p)]
        seg = seg_names[rng.choice(len(seg_names), p=seg_p)]
        first = months[0] if rng.random() < 0.7 else months[int(rng.integers(1, 28))]
        churn = months[int(rng.integers(14, 31))] if rng.random() < 0.14 else None
        n_services = min(len(svc_names), SEGMENT_SERVICE_COUNT[seg] + int(rng.random() < 0.5))
        services = [str(s) for s in rng.choice(svc_names, size=n_services, replace=False)]
        customers.append({
            "customer_id": f"C{i + 1:03d}",
            "customer_name": f"Account {i + 1:03d}",
            "country": c["country"],
            "iso3": c["iso3"],
            "region": c["region"],
            "segment": seg,
            "first_month": str(first),
            "churn_month": str(churn) if churn is not None else None,
            "_services": services,
            "_trend": float(rng.choice([-0.025, 0.0, 0.01, 0.02], p=[0.2, 0.4, 0.25, 0.15])),
            "_factor": float(rng.lognormal(0, 0.25)),
            "_market": float(c["market_size"]),
        })

    # Monthly shipment rows per customer and service.
    ship = []
    for cu in customers:
        seg_scale, discount = SEGMENTS[cu["segment"]][1], SEGMENTS[cu["segment"]][2]
        first_p = pd.Period(cu["first_month"], freq="M")
        churn_p = pd.Period(cu["churn_month"], freq="M") if cu["churn_month"] else None
        for i, m in enumerate(months):
            if m < first_p or (churn_p is not None and m >= churn_p):
                continue
            growth = ((1 + MONTHLY_GROWTH) * (1 + cu["_trend"])) ** i
            for s in cu["_services"]:
                _, price, base = SERVICES[s]
                lam = base * seg_scale * cu["_factor"] * cu["_market"] * SEASONALITY[m.month - 1] * growth
                n = max(int(rng.poisson(max(lam * rng.normal(1, 0.08), 0.5))), 1)
                revenue = round(n * price * discount * rng.normal(1, 0.04), 2)
                ship.append((str(m), cu["customer_id"], s, revenue, n))

    shipments = pd.DataFrame(ship, columns=["month", "customer_id", "service", "revenue", "shipments"])
    public_cols = [k for k in customers[0] if not k.startswith("_")]
    customers_df = pd.DataFrame(customers)[public_cols]

    # Targets: prior-year actual x 1.06 (plus noise), or the actual itself for the first year.
    region_of = dict(zip(customers_df.customer_id, customers_df.region))
    actual = (shipments.assign(region=shipments.customer_id.map(region_of))
              .groupby(["region", "month"])["revenue"].sum().to_dict())
    target_rows = []
    for rg in sorted(countries["region"].unique()):
        for m in _periods(FIRST_MONTH, FORECAST_END):
            prev = str(m - 12)
            if (rg, prev) in actual:
                base = actual[(rg, prev)] * 1.06
            else:
                base = actual.get((rg, str(m)), 0.0)
            target_rows.append((str(m), rg, round(base * rng.uniform(0.96, 1.04), 2)))
    targets = pd.DataFrame(target_rows, columns=["month", "region", "target_revenue"])

    services = pd.DataFrame(
        [(name, cat, price) for name, (cat, price, _) in SERVICES.items()],
        columns=["service_name", "category", "list_price"],
    )
    countries_df = countries.copy()
    info = pd.DataFrame({
        "key": ["banner", "seed", "first_month", "last_month", "forecast_end"],
        "value": [BANNER, str(seed), FIRST_MONTH, LAST_MONTH, FORECAST_END],
    })
    return {
        "countries": countries_df,
        "services": services,
        "customers": customers_df,
        "shipments": shipments,
        "targets": targets,
        "info": info,
    }


def build_database(path: str | Path, seed: int = SEED) -> Path:
    """Create (or rebuild) the SQLite database at ``path``."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    tables = generate(seed)
    with sqlite3.connect(path) as con:
        tables["countries"].to_sql("countries", con, index=False)
        tables["services"].to_sql("services", con, index=False)
        tables["customers"].to_sql("customers", con, index=False)
        tables["shipments"].to_sql("shipments", con, index=False)
        tables["targets"].to_sql("targets", con, index=False)
        tables["info"].to_sql("dataset_info", con, index=False)
        con.executescript(SCHEMA_EXTRAS)
    return path


if __name__ == "__main__":
    out = build_database(Path(__file__).resolve().parent / "data" / "sales_simulated.db")
    print(f"Built simulated database at {out}")
