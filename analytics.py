"""Analysis layer: pure pandas and NumPy functions with no Streamlit dependency, so they can be tested directly."""
from __future__ import annotations

import io

import numpy as np
import pandas as pd
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

CRITICAL, WARNING, OPPORTUNITY, INFO = "critical", "warning", "opportunity", "info"
LEVEL_ORDER = {CRITICAL: 0, WARNING: 1, OPPORTUNITY: 2, INFO: 3}
Z_90_PCT = 1.645  # two-sided 90% band for the forecast, approximate


# ---------- formatting ----------
def fmt_money(v) -> str:
    if v is None or pd.isna(v):
        return "n/a"
    a = abs(v)
    if a >= 1e6:
        return f"${v / 1e6:,.2f}M"
    if a >= 1e3:
        return f"${v / 1e3:,.1f}K"
    return f"${v:,.0f}"


def fmt_pct(v) -> str:
    return "n/a" if v is None or pd.isna(v) else f"{v:.1%}"


# ---------- windows and filters ----------
def filter_sales(df: pd.DataFrame, regions=None, services=None, segments=None) -> pd.DataFrame:
    out = df
    if regions is not None:
        out = out[out["region"].isin(regions)]
    if services is not None:
        out = out[out["service"].isin(services)]
    if segments is not None:
        out = out[out["segment"].isin(segments)]
    return out


def month_window(all_months: list[str], start: str, end: str) -> list[str]:
    return [m for m in all_months if start <= m <= end]


def prior_window(all_months: list[str], start: str, end: str) -> list[str]:
    """The window of equal length immediately before ``start``."""
    n = len(month_window(all_months, start, end))
    i = all_months.index(start)
    return all_months[max(0, i - n):i]


# ---------- executive KPIs ----------
def kpis(cur: pd.DataFrame, prior: pd.DataFrame, cur_targets: pd.DataFrame | None = None) -> dict:
    revenue = float(cur["revenue"].sum())
    shipments = int(cur["shipments"].sum())
    prior_rev = float(prior["revenue"].sum()) if len(prior) else 0.0
    if cur_targets is not None and len(cur_targets):
        target = float(cur_targets["target_revenue"].sum())
    else:
        target = np.nan
    return {
        "revenue": revenue,
        "shipments": shipments,
        "avg_revenue_per_shipment": revenue / shipments if shipments else np.nan,
        "active_customers": int(cur["customer_id"].nunique()),
        "growth": revenue / prior_rev - 1 if prior_rev > 0 else np.nan,
        "target": target,
        "attainment": revenue / target if target and target > 0 else np.nan,
    }


def monthly_summary(sales: pd.DataFrame, targets: pd.DataFrame | None = None) -> pd.DataFrame:
    out = sales.groupby("month", as_index=False).agg(
        revenue=("revenue", "sum"), shipments=("shipments", "sum"), customers=("customer_id", "nunique"))
    if targets is not None and len(targets):
        t = targets.groupby("month", as_index=False)["target_revenue"].sum()
        out = out.merge(t, on="month", how="left")
    return out


# ---------- regional and country analysis ----------
def region_summary(sales: pd.DataFrame, targets: pd.DataFrame | None = None) -> pd.DataFrame:
    out = sales.groupby("region", as_index=False).agg(
        revenue=("revenue", "sum"), shipments=("shipments", "sum"), customers=("customer_id", "nunique"))
    out["avg_revenue_per_shipment"] = out["revenue"] / out["shipments"]
    out["share"] = out["revenue"] / out["revenue"].sum()
    if targets is not None and len(targets):
        t = targets.groupby("region", as_index=False)["target_revenue"].sum()
        out = out.merge(t, on="region", how="left")
        out["attainment"] = out["revenue"] / out["target_revenue"]
    return out.sort_values("revenue", ascending=False).reset_index(drop=True)


def country_summary(sales: pd.DataFrame) -> pd.DataFrame:
    out = sales.groupby(["country", "iso3", "region"], as_index=False).agg(
        revenue=("revenue", "sum"), shipments=("shipments", "sum"), customers=("customer_id", "nunique"))
    out["share"] = out["revenue"] / out["revenue"].sum()
    out["avg_revenue_per_shipment"] = out["revenue"] / out["shipments"]
    return out.sort_values("revenue", ascending=False).reset_index(drop=True)


# ---------- customer analysis ----------
def top_customers(sales: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    total = sales["revenue"].sum()
    out = sales.groupby(["customer_id", "customer_name", "region", "segment"], as_index=False).agg(
        revenue=("revenue", "sum"), shipments=("shipments", "sum"), active_months=("month", "nunique"))
    out["share_of_revenue"] = out["revenue"] / total if total else 0.0
    return out.sort_values("revenue", ascending=False).head(n).reset_index(drop=True)


def customer_status(sales: pd.DataFrame) -> pd.DataFrame:
    """Classify each customer as Active, At risk or Churned, and tier them by total revenue.

    Churned: no shipments in the last three months of data.
    At risk: last three months below half of the three months before.
    """
    cols = ["customer_id", "customer_name", "region", "segment", "total_revenue", "active_months",
            "recent_revenue", "prior_revenue", "avg_monthly_revenue", "status", "value_tier"]
    if sales.empty:
        return pd.DataFrame(columns=cols)
    months = sorted(sales["month"].unique())
    recent, prior = months[-3:], months[-6:-3]
    base = sales.groupby(["customer_id", "customer_name", "region", "segment"], as_index=False).agg(
        total_revenue=("revenue", "sum"), active_months=("month", "nunique"))
    rec = sales[sales["month"].isin(recent)].groupby("customer_id")["revenue"].sum()
    pri = sales[sales["month"].isin(prior)].groupby("customer_id")["revenue"].sum()
    base["recent_revenue"] = base["customer_id"].map(rec).fillna(0.0)
    base["prior_revenue"] = base["customer_id"].map(pri).fillna(0.0)
    base["avg_monthly_revenue"] = base["total_revenue"] / base["active_months"].clip(lower=1)
    base["status"] = np.select(
        [base["recent_revenue"] <= 0,
         (base["prior_revenue"] > 0) & (base["recent_revenue"] < 0.5 * base["prior_revenue"])],
        ["Churned", "At risk"], default="Active")
    q80, q50 = base["total_revenue"].quantile(0.8), base["total_revenue"].quantile(0.5)
    base["value_tier"] = np.select(
        [base["total_revenue"] >= q80, base["total_revenue"] >= q50],
        ["High (top 20%)", "Mid (next 30%)"], default="Low (bottom 50%)")
    return base[cols].sort_values("total_revenue", ascending=False).reset_index(drop=True)


def segment_summary(status: pd.DataFrame) -> pd.DataFrame:
    if status.empty:
        return pd.DataFrame(columns=["segment", "customers", "revenue", "churned", "at_risk",
                                     "revenue_per_customer", "share_of_revenue"])
    g = status.groupby("segment", as_index=False).agg(
        customers=("customer_id", "count"),
        revenue=("total_revenue", "sum"),
        churned=("status", lambda s: int((s == "Churned").sum())),
        at_risk=("status", lambda s: int((s == "At risk").sum())),
    )
    g["revenue_per_customer"] = g["revenue"] / g["customers"]
    g["share_of_revenue"] = g["revenue"] / g["revenue"].sum()
    return g


def frequency_summary(sales: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Shipping frequency per customer within the window, plus headline repeat statistics."""
    per = sales.groupby("customer_id").agg(
        active_months=("month", "nunique"), shipments=("shipments", "sum")).reset_index()
    if per.empty:
        return per, {"repeat_rate": np.nan, "avg_active_months": np.nan, "avg_shipments_per_month": np.nan}
    per["shipments_per_active_month"] = per["shipments"] / per["active_months"]
    stats = {
        "repeat_rate": float((per["active_months"] >= 2).mean()),
        "avg_active_months": float(per["active_months"].mean()),
        "avg_shipments_per_month": float(per["shipments_per_active_month"].mean()),
    }
    return per, stats


def retention_table(sales: pd.DataFrame) -> pd.DataFrame:
    """Month-on-month retention. A customer lapses when they ship in one month and not the next."""
    rows, prev = [], None
    for m in sorted(sales["month"].unique()):
        active = set(sales.loc[sales["month"] == m, "customer_id"])
        if prev is not None and prev:
            kept = len(active & prev)
            rows.append({
                "month": m,
                "active": len(active),
                "new": len(active - prev),
                "lapsed": len(prev - active),
                "retention_rate": kept / len(prev),
                "churn_rate": len(prev - active) / len(prev),
            })
        prev = active
    return pd.DataFrame(rows, columns=["month", "active", "new", "lapsed", "retention_rate", "churn_rate"])


# ---------- service analysis ----------
def service_summary(sales: pd.DataFrame) -> pd.DataFrame:
    g = sales.groupby(["service", "category"], as_index=False).agg(
        revenue=("revenue", "sum"), shipments=("shipments", "sum"), customers=("customer_id", "nunique"))
    g["avg_revenue_per_shipment"] = g["revenue"] / g["shipments"]
    g["revenue_share"] = g["revenue"] / g["revenue"].sum()
    g["shipment_share"] = g["shipments"] / g["shipments"].sum()
    return g.sort_values("revenue", ascending=False).reset_index(drop=True)


# ---------- forecasting ----------
def seasonal_forecast(history: pd.Series, horizon: int = 6) -> pd.DataFrame:
    """Linear trend multiplied by calendar-month seasonality learned from the history.

    ``history`` is revenue indexed by 'YYYY-MM' strings, in time order. Seasonality is
    only estimated when there are at least 24 months; otherwise it is flat. The band is an
    approximate 90% interval from the residual standard deviation.
    """
    if len(history) < 3:
        raise ValueError("At least three months of history are needed to forecast.")
    periods = pd.PeriodIndex(history.index, freq="M")
    y = history.to_numpy(dtype=float)
    t = np.arange(len(y))
    slope, intercept = np.polyfit(t, y, 1)
    trend = intercept + slope * t
    if len(y) >= 24:
        ratio = pd.Series(y / trend, index=periods.month)
        cal = ratio.groupby(level=0).mean()
        cal = cal / cal.mean()
    else:
        cal = pd.Series(1.0, index=range(1, 13))
    fitted = trend * cal.reindex(periods.month).to_numpy()
    resid_sd = float(np.std(y - fitted, ddof=2)) if len(y) > 3 else 0.0
    future = pd.period_range(periods[-1] + 1, periods=horizon, freq="M")
    tf = np.arange(len(y), len(y) + horizon)
    fc = (intercept + slope * tf) * cal.reindex(future.month).to_numpy()
    return pd.DataFrame({
        "month": future.astype(str),
        "forecast": fc,
        "lower": fc - Z_90_PCT * resid_sd,
        "upper": fc + Z_90_PCT * resid_sd,
    })


def backtest(history: pd.Series, horizon: int = 6) -> pd.DataFrame:
    """Hold out the last ``horizon`` months, forecast them from earlier data, and compare."""
    if len(history) < horizon + 6:
        raise ValueError("Not enough history for a backtest.")
    train, test = history.iloc[:-horizon], history.iloc[-horizon:]
    fc = seasonal_forecast(train, horizon)
    out = fc.assign(actual=test.to_numpy(dtype=float))
    out["gap"] = out["actual"] - out["forecast"]
    out["gap_pct"] = out["gap"] / out["forecast"]
    out["status"] = np.where(out["actual"] < out["lower"], "Below band",
                             np.where(out["actual"] > out["upper"], "Above band", "Within band"))
    return out


def forecast_vs_target(fc: pd.DataFrame, targets: pd.DataFrame | None = None) -> pd.DataFrame:
    out = fc.copy()
    if targets is not None and len(targets):
        out = out.merge(targets[["month", "target_revenue"]], on="month", how="left")
    else:
        out["target_revenue"] = np.nan
    out["gap_vs_target"] = out["forecast"] - out["target_revenue"]
    out["gap_pct"] = out["gap_vs_target"] / out["target_revenue"]
    out["flag"] = np.where(out["target_revenue"].isna(), "No target",
                           np.where(out["gap_vs_target"] < 0, "Revenue gap", "On or above target"))
    return out


# ---------- management insights (rule-based, thresholds stated in the UI) ----------
def generate_insights(sales: pd.DataFrame, targets: pd.DataFrame | None = None,
                      forecast_table: pd.DataFrame | None = None) -> list[dict]:
    months = sorted(sales["month"].unique())
    if len(months) < 6:
        return [dict(level=INFO, title="Not enough history",
                     evidence="At least six months are needed to compare recent and earlier periods.",
                     action="Widen the date range in the sidebar.")]
    recent, prior = months[-3:], months[-6:-3]
    insights: list[dict] = []
    recent_sales = sales[sales["month"].isin(recent)]
    run_rate = float(recent_sales["revenue"].sum()) * 4

    # 1. Regional trend: last three months against the three before.
    reg_recent = recent_sales.groupby("region")["revenue"].sum()
    reg_prior = sales[sales["month"].isin(prior)].groupby("region")["revenue"].sum()
    for rg, rec_value in reg_recent.items():
        pri_value = reg_prior.get(rg, 0.0)
        if pri_value <= 0:
            continue
        change = rec_value / pri_value - 1
        if change <= -0.05:
            insights.append(dict(level=WARNING, title=f"Revenue falling in {rg}",
                                 evidence=f"Last three months are {change:+.1%} against the three months before.",
                                 action=f"Review the largest {rg} accounts first, and call those whose volumes have dropped."))
        elif change >= 0.10:
            insights.append(dict(level=OPPORTUNITY, title=f"Growth in {rg}",
                                 evidence=f"Last three months are {change:+.1%} against the three months before.",
                                 action=f"Check whether sales capacity and pricing in {rg} can keep up with demand."))

    # 2. Target attainment by region (only meaningful when the selection is the whole region).
    if targets is not None and len(targets):
        t_recent = targets[targets["month"].isin(recent)].groupby("region")["target_revenue"].sum()
        for rg, target in t_recent.items():
            if target <= 0 or rg not in reg_recent.index:
                continue
            att = reg_recent[rg] / target
            if att < 0.95:
                insights.append(dict(level=CRITICAL, title=f"{rg} is missing target",
                                     evidence=f"Attainment is {att:.0%} over the last three months.",
                                     action="Agree a recovery plan with the regional lead, and review pipeline coverage for next quarter."))

    # 3. Churn and at-risk accounts.
    status = customer_status(sales)
    churned = status[status["status"] == "Churned"]
    if len(churned):
        lost = float((churned["total_revenue"] / churned["active_months"].clip(lower=1)).sum() * 12)
        if run_rate > 0 and lost / run_rate >= 0.03:
            noun = "account has" if len(churned) == 1 else "accounts have"
            insights.append(dict(level=CRITICAL, title=f"{len(churned)} {noun} churned",
                                 evidence=f"Their average monthly revenue, annualised, is about {fmt_money(lost)}, "
                                          f"or {lost / run_rate:.0%} of the current annual run rate.",
                                 action="Run exit reviews with the largest churned accounts, and record which service or lane they stopped using."))
    at_risk = status[status["status"] == "At risk"]
    if len(at_risk):
        noun = "account is" if len(at_risk) == 1 else "accounts are"
        insights.append(dict(level=WARNING, title=f"{len(at_risk)} {noun} at risk",
                             evidence="Revenue in the last three months is under half of the three months before.",
                             action="Assign account reviews this week to the at-risk accounts, ranked by prior revenue."))

    # 4. Concentration.
    total = float(sales["revenue"].sum())
    top10 = float(sales.groupby("customer_id")["revenue"].sum().nlargest(10).sum())
    if total > 0 and top10 / total > 0.35:
        insights.append(dict(level=WARNING, title=f"Top 10 accounts are {top10 / total:.0%} of revenue",
                             evidence="Losing one large account would move the total noticeably.",
                             action="Build pipeline in the mid-market and SME segments to reduce dependence on a few accounts."))

    # 5. Service mix opportunity.
    svc = service_summary(recent_sales) if len(recent_sales) else pd.DataFrame()
    if len(svc):
        best = svc.sort_values("avg_revenue_per_shipment", ascending=False).iloc[0]
        if best["shipment_share"] < 0.15:
            insights.append(dict(level=OPPORTUNITY, title=f"{best['service']} earns the most per shipment",
                                 evidence=f"{fmt_money(best['avg_revenue_per_shipment'])} per shipment, "
                                          f"but only {best['shipment_share']:.0%} of recent shipments.",
                                 action="Offer this service to existing accounts that ship lower-value services."))

    # 6. Forward forecast against target.
    if forecast_table is not None and len(forecast_table) and forecast_table["target_revenue"].notna().any():
        tgt = float(forecast_table["target_revenue"].sum())
        fc = float(forecast_table["forecast"].sum())
        gap = (fc - tgt) / tgt
        if gap < -0.03:
            insights.append(dict(level=WARNING, title="Forecast is below target",
                                 evidence=f"The next {len(forecast_table)} months forecast {gap:.1%} against target.",
                                 action="Build a recovery plan for the gap, starting with the regions that show the largest shortfall."))
        elif gap > 0.03:
            insights.append(dict(level=INFO, title="Forecast is ahead of target",
                                 evidence=f"The next {len(forecast_table)} months forecast {gap:+.1%} against target.",
                                 action="Confirm capacity can support the forecast, and protect the margin on the volume."))

    return sorted(insights, key=lambda d: LEVEL_ORDER[d["level"]])


# ---------- export ----------
def build_export(tables: dict[str, pd.DataFrame]) -> bytes:
    """Write each table to its own sheet of an Excel workbook, with bold headers and sized columns."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, df in tables.items():
            sheet = name[:31]
            df.to_excel(xw, sheet_name=sheet, index=False)
            ws = xw.sheets[sheet]
            ws.freeze_panes = "A2"
            for ci, col in enumerate(df.columns, start=1):
                values = [str(col)] + [str(v) for v in df[col].head(200)]
                ws.column_dimensions[get_column_letter(ci)].width = min(max(len(v) for v in values) + 2, 48)
            for cell in ws[1]:
                cell.font = Font(bold=True)
    return buf.getvalue()
