"""Sales Performance Intelligence: Streamlit front end.

All figures are simulated. The colour scheme takes inspiration from DHL's red and yellow.
This application is not affiliated with or endorsed by DHL.
"""
from __future__ import annotations

import html

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import analytics as an
import db
from data_gen import BANNER

st.set_page_config(page_title="Sales Performance Intelligence (Simulated)", layout="wide")

RED, YELLOW, AMBER = "#D40511", "#FFCC00", "#E6A800"
INK, GREY, GREEN = "#1F1F1F", "#5F6368", "#1E7B3C"
PALETTE = [RED, AMBER, GREY, "#8C8C8C", "#7A1C1C", "#FFE27A"]
STATUS_COLORS = {"Active": GREY, "At risk": AMBER, "Churned": RED}
SEGMENT_NAMES = ["Enterprise", "Mid-Market", "SME"]
PAGES = ["Executive overview", "Regional analysis", "Customer analysis",
         "Service analysis", "Sales forecast", "Management insights"]

CSS = f"""
<style>
.hero {{background:{RED};color:#fff;padding:18px 24px;border-bottom:6px solid {YELLOW};border-radius:8px;margin-bottom:12px}}
.hero h1 {{margin:0;font-size:1.6rem;font-weight:700;color:#fff}}
.hero p {{margin:4px 0 0 0;color:#fff;opacity:.95}}
.badge {{display:inline-block;background:{YELLOW};color:{INK};font-weight:700;font-size:.72rem;padding:2px 8px;border-radius:4px;margin-left:8px;vertical-align:middle}}
.simnote {{background:#FFF6CC;border:1px solid {YELLOW};border-radius:6px;padding:8px 12px;font-size:.85rem;color:{INK};margin-bottom:12px}}
.kpi {{background:#fff;color:{INK};border:1px solid #E3E3E3;border-top:4px solid {RED};border-radius:8px;padding:14px 16px;min-height:132px;display:flex;flex-direction:column;justify-content:space-between}}
.kpi .label {{color:{GREY};font-size:.78rem;text-transform:uppercase;letter-spacing:.04em}}
.kpi .value {{color:{INK};font-size:1.55rem;font-weight:700;margin-top:4px;font-variant-numeric:tabular-nums}}
.kpi .delta {{font-size:.84rem;margin-top:2px;color:{GREY}}}
.kpi .delta.up {{color:{GREEN}}}
.kpi .delta.down {{color:{RED}}}
.insight {{background:#fff;color:{INK};border:1px solid #E3E3E3;border-left:6px solid {GREY};border-radius:6px;padding:12px 14px;margin-bottom:10px}}
.insight.critical {{border-left-color:{RED}}}
.insight.warning {{border-left-color:{AMBER}}}
.insight.opportunity {{border-left-color:{GREEN}}}
.insight .tag {{font-size:.72rem;text-transform:uppercase;letter-spacing:.05em;color:{GREY}}}
.insight .action {{margin-top:6px}}
</style>
"""
PRO_CSS = f"""
<style>
#MainMenu, footer {{visibility: hidden;}}
.block-container {{padding-top: 1.6rem; padding-bottom: 2rem; max-width: 1280px;}}
[data-testid="stSidebar"] {{background: #F7F7F5; border-right: 1px solid #E6E6E6;}}
[data-testid="stSidebar"] h3 {{color: {RED}; font-size: 1.05rem; letter-spacing: .01em; margin-bottom: .25rem;}}
h3 {{font-size: 1.05rem !important; font-weight: 700; color: {INK}; border-left: 4px solid {RED};
     padding-left: 10px; margin-top: 1.4rem !important; margin-bottom: .6rem !important;}}
.hero {{padding: 16px 22px; box-shadow: 0 1px 3px rgba(0,0,0,.08);}}
.kpi {{box-shadow: 0 1px 3px rgba(0,0,0,.06); transition: box-shadow .15s ease;}}
.kpi:hover {{box-shadow: 0 6px 16px rgba(0,0,0,.09);}}
.insight {{box-shadow: 0 1px 2px rgba(0,0,0,.04);}}
div[data-testid="stDownloadButton"] button {{background: {RED}; color: #fff; border: none; font-weight: 600;}}
div[data-testid="stDownloadButton"] button:hover {{background: #A8040E; color: #fff; border: none;}}
div[data-testid="stDataFrame"] {{border: 1px solid #E6E6E6; border-radius: 8px;}}
div[data-testid="stAlert"] {{border-radius: 8px;}}
[data-testid="stCaptionContainer"] {{color: {GREY};}}
hr {{border-color: #E6E6E6;}}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)
st.markdown(PRO_CSS, unsafe_allow_html=True)


# ---------- helpers ----------
def style(fig, height: int = 340):
    fig.update_layout(template="plotly_white", font=dict(family="Arial", color=INK), colorway=PALETTE,
                      height=height, margin=dict(l=10, r=10, t=40, b=10),
                      paper_bgcolor="white", plot_bgcolor="white",
                      title=dict(font=dict(size=14, color=INK), x=0, xanchor="left"),
                      xaxis=dict(gridcolor="#EFEFEF", linecolor="#DDDDDD"),
                      yaxis=dict(gridcolor="#EFEFEF", zerolinecolor="#DDDDDD"),
                      hoverlabel=dict(bgcolor="white", font=dict(color=INK)),
                      legend=dict(orientation="h", y=-0.15))
    return fig


def kpi(label: str, value: str, sub: str = "", tone: str = "") -> None:
    st.markdown(
        f'<div class="kpi"><div class="label">{html.escape(label)}</div>'
        f'<div class="value">{html.escape(value)}</div>'
        f'<div class="delta {tone}">{html.escape(sub)}</div></div>',
        unsafe_allow_html=True)


def display(df: pd.DataFrame, money=(), pct=(), ints=(), rename=None) -> pd.DataFrame:
    out = df.copy()
    for c in money:
        if c in out:
            out[c] = out[c].map(an.fmt_money)
    for c in pct:
        if c in out:
            out[c] = out[c].map(an.fmt_pct)
    for c in ints:
        if c in out:
            out[c] = out[c].map(lambda v: f"{v:,.0f}" if pd.notna(v) else "n/a")
    return out.rename(columns=rename or {})


@st.cache_data(show_spinner="Loading simulated dataset...")
def load_data():
    db.ensure_database()
    return db.load_sales(), db.load_targets(), db.load_customers(), db.load_services(), db.load_info()


sales_all, targets_all, customers_all, services_all, info_all = load_data()
months = sorted(sales_all["month"].unique())
REGIONS = sorted(sales_all["region"].unique())
SERVICE_NAMES = sorted(sales_all["service"].unique())

# ---------- sidebar: navigation and filters ----------
with st.sidebar:
    st.markdown("### Sales Performance Intelligence")
    page = st.radio("Section", PAGES, label_visibility="collapsed")
    st.markdown("---")
    st.markdown("**Filters**")
    start = st.selectbox("From", months, index=max(0, len(months) - 12))
    end = st.selectbox("To", months, index=len(months) - 1)
    sel_regions = st.multiselect("Region", REGIONS, default=REGIONS)
    sel_services = st.multiselect("Service", SERVICE_NAMES, default=SERVICE_NAMES)
    sel_segments = st.multiselect("Customer segment", SEGMENT_NAMES, default=SEGMENT_NAMES)

if start > end:
    st.error("The start month is after the end month. Choose a valid range.")
    st.stop()
if not (sel_regions and sel_services and sel_segments):
    st.warning("Select at least one region, service and segment.")
    st.stop()

# ---------- derived data ----------
cur_months = an.month_window(months, start, end)
prior_months = an.prior_window(months, start, end)
full = set(sel_services) == set(SERVICE_NAMES) and set(sel_segments) == set(SEGMENT_NAMES)
f_all = an.filter_sales(sales_all, sel_regions, sel_services, sel_segments)
upto = f_all[f_all["month"] <= end]
cur = f_all[f_all["month"].isin(cur_months)]
prior = f_all[f_all["month"].isin(prior_months)]
t_regions = targets_all[targets_all["region"].isin(sel_regions)]
t_cur = t_regions[t_regions["month"].isin(cur_months)] if full else None
region_label = "All regions" if set(sel_regions) == set(REGIONS) else ", ".join(sel_regions)

if cur.empty:
    st.info("No sales in this selection. Widen the date range or the filters.")
    st.stop()


def forecast_inputs(horizon: int):
    hist = upto.groupby("month")["revenue"].sum().sort_index()
    fc = an.seasonal_forecast(hist, horizon)
    tgt = None
    if full:
        tgt = t_regions.groupby("month", as_index=False)["target_revenue"].sum()
    return hist, fc, an.forecast_vs_target(fc, tgt)


K = an.kpis(cur, prior, t_cur)

with st.sidebar:
    st.markdown("---")
    _, _, fvt_default = forecast_inputs(6) if len(upto.month.unique()) >= 6 else (None, None, pd.DataFrame())
    export_tables = {
        "README": pd.DataFrame({"Notice": [
            BANNER,
            "Figures are generated for this demonstration and are not DHL company performance.",
            "Inspired by DHL colours. Not affiliated with or endorsed by DHL.",
            f"Period: {start} to {end}",
            f"Regions: {region_label}",
        ]}),
        "KPIs": pd.DataFrame([K]),
        "Monthly": an.monthly_summary(cur, t_cur),
        "Regions": an.region_summary(cur, t_cur),
        "Countries": an.country_summary(cur),
        "Top customers": an.top_customers(cur, 10),
        "Customer status": an.customer_status(upto),
        "Services": an.service_summary(cur),
        "Forecast": fvt_default,
    }
    st.download_button(
        "Download Excel report",
        data=an.build_export(export_tables),
        file_name=f"sales_intelligence_simulated_{start}_{end}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    st.caption("Downloads are built from the current filters.")

# ---------- header ----------
st.markdown(
    f'<div class="hero"><h1>Sales Performance Intelligence <span class="badge">SIMULATED DATA</span></h1>'
    f'<p>{html.escape(page)} &middot; {html.escape(start)} to {html.escape(end)} &middot; '
    f'{html.escape(region_label)}</p></div>',
    unsafe_allow_html=True)
if not full:
    st.caption("Targets are set by region only. Target and attainment figures are hidden while "
               "service or segment filters are partial.")


# ---------- pages ----------
def page_overview():
    growth = K["growth"]
    tone = "" if pd.isna(growth) else ("up" if growth >= 0 else "down")
    cols = st.columns(6)
    with cols[0]:
        kpi("Total revenue", an.fmt_money(K["revenue"]), f"{len(cur_months)} months")
    with cols[1]:
        kpi("Total shipments", f"{K['shipments']:,}", "shipments in period")
    with cols[2]:
        kpi("Revenue per shipment", an.fmt_money(K["avg_revenue_per_shipment"]), "average")
    with cols[3]:
        kpi("Active customers", f"{K['active_customers']:,}", "shipped in period")
    with cols[4]:
        kpi("Revenue growth", "n/a" if pd.isna(growth) else f"{growth:+.1%}",
            "No prior window in data" if pd.isna(growth) else f"vs prior {len(prior_months)} months", tone)
    with cols[5]:
        kpi("Target achievement", an.fmt_pct(K["attainment"]) if t_cur is not None else "Partial filter",
            an.fmt_money(K["target"]) + " target" if t_cur is not None else "Set by region only")

    m = an.monthly_summary(cur, t_cur)
    fig = go.Figure(go.Bar(x=m["month"], y=m["revenue"], name="Revenue", marker_color=RED))
    if "target_revenue" in m.columns and m["target_revenue"].notna().any():
        fig.add_trace(go.Scatter(x=m["month"], y=m["target_revenue"], name="Target", mode="lines+markers",
                                 line=dict(color=INK, dash="dash")))
    fig.update_layout(yaxis_tickprefix="$", title="Monthly revenue against target")
    st.plotly_chart(style(fig, 360), use_container_width=True)

    fig2 = go.Figure(go.Bar(x=m["month"], y=m["shipments"], name="Shipments", marker_color=AMBER))
    fig2.update_layout(title="Monthly shipments")
    st.plotly_chart(style(fig2, 260), use_container_width=True)


def page_regions():
    reg = an.region_summary(cur, t_cur)
    ctry = an.country_summary(cur)
    metric = "attainment" if (t_cur is not None and "attainment" in reg.columns) else "revenue"
    st.subheader("Revenue by country")
    fig = px.choropleth(ctry, locations="iso3", color="revenue", hover_name="country",
                        hover_data={"iso3": False, "revenue": ":$,.0f", "region": True},
                        color_continuous_scale=["#FFF3C4", RED], projection="natural earth")
    fig.update_layout(coloraxis_colorbar=dict(title="Revenue"))
    st.plotly_chart(style(fig, 420), use_container_width=True)

    st.subheader("Regional comparison")
    ranked = reg.sort_values(metric, ascending=False)
    fig2 = go.Figure(go.Bar(x=ranked["region"], y=ranked["revenue"], marker_color=RED,
                            text=ranked["share"].map(an.fmt_pct), textposition="outside"))
    fig2.update_layout(yaxis_tickprefix="$", title="Revenue by region (label shows share)")
    st.plotly_chart(style(fig2, 320), use_container_width=True)

    if len(ranked) > 1:
        best, worst = ranked.iloc[0], ranked.iloc[-1]
        label = "attainment" if metric == "attainment" else "revenue"
        c1, c2 = st.columns(2)
        with c1:
            kpi("Highest performing region", str(best["region"]),
                f"{an.fmt_pct(best[metric]) if metric == 'attainment' else an.fmt_money(best['revenue'])} {label}")
        with c2:
            kpi("Lowest performing region", str(worst["region"]),
                f"{an.fmt_pct(worst[metric]) if metric == 'attainment' else an.fmt_money(worst['revenue'])} {label}",
                "down")

    if len(ctry) > 1:
        top_c, low_c = ctry.iloc[0], ctry.iloc[-1]
        c3, c4 = st.columns(2)
        with c3:
            kpi("Highest revenue country", str(top_c["country"]), an.fmt_money(top_c["revenue"]))
        with c4:
            kpi("Lowest revenue country", str(low_c["country"]), an.fmt_money(low_c["revenue"]), "down")

    st.subheader("Region table")
    st.dataframe(display(reg, money=["revenue", "target_revenue", "avg_revenue_per_shipment"],
                         pct=["share", "attainment"], ints=["shipments", "customers"],
                         rename={"target_revenue": "target"}), hide_index=True, use_container_width=True)
    st.subheader("Country table")
    st.dataframe(display(ctry, money=["revenue", "avg_revenue_per_shipment"], pct=["share"],
                         ints=["shipments", "customers"]), hide_index=True, use_container_width=True)


def page_customers():
    status = an.customer_status(upto)
    top = an.top_customers(cur, 10)
    counts = status["status"].value_counts()
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi("Active", f"{int(counts.get('Active', 0)):,}", "customers")
    with c2:
        kpi("At risk", f"{int(counts.get('At risk', 0)):,}", "revenue under half of prior 3 months", "down")
    with c3:
        kpi("Churned", f"{int(counts.get('Churned', 0)):,}", "no shipments in last 3 months", "down")
    with c4:
        rets = an.retention_table(cur)
        latest = rets["retention_rate"].iloc[-1] if len(rets) else float("nan")
        kpi("Retention, latest month", an.fmt_pct(latest), "customers kept from prior month")

    st.subheader("Top 10 customers by revenue")
    fig = go.Figure(go.Bar(x=top["revenue"], y=top["customer_name"], orientation="h", marker_color=RED,
                           text=top["share_of_revenue"].map(an.fmt_pct), textposition="outside"))
    fig.update_layout(yaxis=dict(autorange="reversed"), xaxis_tickprefix="$", title="Label shows share of revenue")
    st.plotly_chart(style(fig, 380), use_container_width=True)
    st.dataframe(display(top, money=["revenue"], pct=["share_of_revenue"], ints=["shipments", "active_months"]),
                 hide_index=True, use_container_width=True)

    st.subheader("Customer segmentation")
    seg = an.segment_summary(status)
    left, right = st.columns([3, 2])
    with left:
        active = status[status["active_months"] > 0]
        fig2 = px.scatter(active, x="avg_monthly_revenue", y="active_months", color="status",
                          size="total_revenue", size_max=22, hover_name="customer_name",
                          hover_data={"region": True, "segment": True, "total_revenue": ":$,.0f"},
                          color_discrete_map=STATUS_COLORS,
                          labels={"avg_monthly_revenue": "Average monthly revenue", "active_months": "Months shipped"},
                          title="Customers by value and shipping frequency")
        st.plotly_chart(style(fig2, 380), use_container_width=True)
    with right:
        st.dataframe(display(seg, money=["revenue", "revenue_per_customer"], pct=["share_of_revenue"],
                             ints=["customers", "churned", "at_risk"]),
                     hide_index=True, use_container_width=True)
        tiers = status["value_tier"].value_counts().reindex(["High (top 20%)", "Mid (next 30%)", "Low (bottom 50%)"]).fillna(0)
        st.caption("Value tiers by total revenue")
        st.dataframe(pd.DataFrame({"Tier": tiers.index, "Customers": tiers.values.astype(int)}),
                     hide_index=True, use_container_width=True)

    st.subheader("Repeat shipping and retention")
    freq, stats = an.frequency_summary(cur)
    c5, c6, c7 = st.columns(3)
    with c5:
        kpi("Repeat shippers", an.fmt_pct(stats["repeat_rate"]), "shipped in 2+ months of the window")
    with c6:
        kpi("Average months shipped", f"{stats['avg_active_months']:.1f}" if pd.notna(stats["avg_active_months"]) else "n/a")
    with c7:
        kpi("Shipments per active month", f"{stats['avg_shipments_per_month']:.1f}" if pd.notna(stats["avg_shipments_per_month"]) else "n/a")
    left2, right2 = st.columns(2)
    with left2:
        if len(freq):
            fig3 = px.histogram(freq, x="active_months", title="Customers by months shipped in the window",
                                labels={"active_months": "Months shipped"})
            st.plotly_chart(style(fig3, 300), use_container_width=True)
    with right2:
        if len(rets):
            fig4 = go.Figure()
            fig4.add_trace(go.Scatter(x=rets["month"], y=rets["retention_rate"], mode="lines+markers",
                                      name="Retention", line=dict(color=GREEN)))
            fig4.add_trace(go.Bar(x=rets["month"], y=rets["churn_rate"], name="Lapsed share", marker_color=RED, opacity=0.5))
            fig4.update_layout(yaxis_tickformat=".0%", title="Retention and lapsed share by month")
            st.plotly_chart(style(fig4, 300), use_container_width=True)
        else:
            st.info("Select at least two months to see retention.")


def page_services():
    svc = an.service_summary(cur)
    st.subheader("Services compared")
    c1, c2 = st.columns(2)
    with c1:
        fig = go.Figure(go.Bar(x=svc["service"], y=svc["revenue"], marker_color=RED, name="Revenue"))
        fig.update_layout(yaxis_tickprefix="$", title="Revenue by service")
        st.plotly_chart(style(fig, 320), use_container_width=True)
    with c2:
        fig = go.Figure(go.Bar(x=svc["service"], y=svc["shipments"], marker_color=AMBER, name="Shipments"))
        fig.update_layout(title="Shipment volume by service")
        st.plotly_chart(style(fig, 320), use_container_width=True)
    fig3 = go.Figure(go.Bar(x=svc["service"], y=svc["avg_revenue_per_shipment"], marker_color=GREY,
                            name="Revenue per shipment"))
    fig3.update_layout(yaxis_tickprefix="$", title="Average revenue per shipment")
    st.plotly_chart(style(fig3, 300), use_container_width=True)
    st.dataframe(display(svc, money=["revenue", "avg_revenue_per_shipment"], pct=["revenue_share", "shipment_share"],
                         ints=["shipments", "customers"]), hide_index=True, use_container_width=True)
    cat = an.service_summary(cur).groupby("category", as_index=False)[["revenue", "shipments"]].sum()
    st.caption("By category: " + "; ".join(f"{r.category} {an.fmt_money(r.revenue)} from {int(r.shipments):,} shipments"
                                           for r in cat.itertuples()))


def page_forecast():
    horizon = st.slider("Forecast horizon (months)", 3, 6, 6)
    hist_len = len(upto["month"].unique())
    if hist_len < 6:
        st.info("At least six months of history are needed. Widen the date range.")
        return
    hist, fc, fvt = forecast_inputs(horizon)
    st.caption(f"Trend and seasonality are learned from {len(hist)} months of history up to {end}. "
               + ("Seasonality is estimated from 24+ months." if len(hist) >= 24
                  else "Seasonality is flat because fewer than 24 months are available."))

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hist.index, y=hist.values, name="Actual", mode="lines+markers", line=dict(color=INK)))
    fig.add_trace(go.Scatter(x=fc["month"], y=fc["lower"], line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=fc["month"], y=fc["upper"], fill="tonexty", fillcolor="rgba(212,5,17,0.12)",
                             line=dict(width=0), name="Approx. 90% band"))
    fig.add_trace(go.Scatter(x=fc["month"], y=fc["forecast"], name="Forecast", mode="lines+markers",
                             line=dict(color=RED, dash="dash")))
    if fvt["target_revenue"].notna().any():
        fig.add_trace(go.Scatter(x=fvt["month"], y=fvt["target_revenue"], name="Target", mode="markers",
                                 marker=dict(color=YELLOW, size=12, line=dict(color=INK, width=1), symbol="diamond")))
    fig.update_layout(yaxis_tickprefix="$", title="Actual revenue, forecast and target")
    st.plotly_chart(style(fig, 380), use_container_width=True)

    total_fc = float(fvt["forecast"].sum())
    c1, c2, c3 = st.columns(3)
    with c1:
        kpi(f"Forecast, next {horizon} months", an.fmt_money(total_fc))
    with c2:
        if fvt["target_revenue"].notna().any():
            tgt_total = float(fvt["target_revenue"].sum())
            gap = total_fc - tgt_total
            kpi("Target for same months", an.fmt_money(tgt_total),
                f"Forecast gap {an.fmt_money(gap)} ({gap / tgt_total:+.1%})", "down" if gap < 0 else "up")
        else:
            kpi("Target for same months", "n/a", "Set by region only; use all services and segments")
    with c3:
        gaps = int((fvt["flag"] == "Revenue gap").sum())
        kpi("Months with a revenue gap", f"{gaps} of {horizon}", "forecast below target", "down" if gaps else "up")

    st.subheader("Forecast against target")
    st.dataframe(display(fvt.assign(gap_pct=fvt["gap_pct"]),
                         money=["forecast", "lower", "upper", "target_revenue", "gap_vs_target"],
                         pct=["gap_pct"], rename={"target_revenue": "target"}),
                 hide_index=True, use_container_width=True)

    st.subheader("Backtest: how well would this model have forecast the last months?")
    if len(hist) >= horizon + 6:
        bt = an.backtest(hist, horizon)
        within = int((bt["status"] == "Within band").sum())
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=bt["month"], y=bt["upper"], line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig2.add_trace(go.Scatter(x=bt["month"], y=bt["lower"], fill="tonexty", fillcolor="rgba(212,5,17,0.12)",
                                  line=dict(width=0), name="Approx. 90% band"))
        fig2.add_trace(go.Scatter(x=bt["month"], y=bt["forecast"], name="Forecast", line=dict(color=RED, dash="dash")))
        fig2.add_trace(go.Scatter(x=bt["month"], y=bt["actual"], name="Actual", mode="lines+markers", line=dict(color=INK)))
        fig2.update_layout(yaxis_tickprefix="$", title=f"Last {horizon} months held out and forecast from earlier data")
        st.plotly_chart(style(fig2, 320), use_container_width=True)
        st.caption(f"{within} of {horizon} held-out months fell inside the band. Months outside it are the gaps "
                   "the model did not anticipate and are worth investigating.")
        st.dataframe(display(bt, money=["forecast", "lower", "upper", "actual", "gap"], pct=["gap_pct"]),
                     hide_index=True, use_container_width=True)
    else:
        st.info("The backtest needs at least horizon + 6 months of history.")
    st.caption("Method: linear trend multiplied by calendar-month seasonality. A simple, transparent baseline, "
               "not a substitute for a driver-based plan.")


def page_insights():
    hist, fc6, fvt6 = forecast_inputs(6) if len(upto["month"].unique()) >= 6 else (None, None, None)
    targets_for_insights = t_regions if full else None
    insights = an.generate_insights(upto, targets_for_insights,
                                    fvt6 if (fvt6 is not None and full) else None)
    counts = pd.Series([i["level"] for i in insights]).value_counts() if insights else pd.Series(dtype=int)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        kpi("Critical", str(int(counts.get("critical", 0))), "act this week", "down")
    with c2:
        kpi("Warnings", str(int(counts.get("warning", 0))), "watch closely")
    with c3:
        kpi("Opportunities", str(int(counts.get("opportunity", 0))), "growth to pursue", "up")
    with c4:
        kpi("Information", str(int(counts.get("info", 0))), "context")

    st.subheader("What the data says")
    labels = {"critical": "Critical", "warning": "Warning", "opportunity": "Opportunity", "info": "Information"}
    for ins in insights:
        st.markdown(
            f'<div class="insight {ins["level"]}"><div class="tag">{labels[ins["level"]]}</div>'
            f'<div><b>{html.escape(ins["title"])}</b></div>'
            f'<div>{html.escape(ins["evidence"])}</div>'
            f'<div class="action"><b>Recommended action:</b> {html.escape(ins["action"])}</div></div>',
            unsafe_allow_html=True)

    st.subheader("Recommended actions, in priority order")
    if insights:
        for n, ins in enumerate(insights, start=1):
            st.markdown(f"{n}. **{ins['title']}**: {ins['action']}")
    else:
        st.write("No rules were triggered for this selection.")

    with st.expander("How these insights are produced"):
        st.markdown(
            "- **Regional trend:** last three months against the three before. Falling by 5% or more is a warning; growing by 10% or more is an opportunity.\n"
            "- **Target:** attainment under 95% over the last three months is critical. Only shown when all services and segments are selected.\n"
            "- **Churn:** churned accounts whose annualised average revenue is at least 3% of the current run rate are critical.\n"
            "- **At-risk accounts:** last three months under half of the three months before.\n"
            "- **Concentration:** top 10 accounts above 35% of revenue.\n"
            "- **Service mix:** the highest revenue-per-shipment service, when it carries under 15% of recent shipments.\n"
            "- **Forecast:** six-month forecast more than 3% below or above target.\n\n"
            "These are transparent rules, not a machine-learning model. Thresholds are judgement calls and can be changed in `analytics.py`.")


PAGE_FUNCS = {
    "Executive overview": page_overview,
    "Regional analysis": page_regions,
    "Customer analysis": page_customers,
    "Service analysis": page_services,
    "Sales forecast": page_forecast,
    "Management insights": page_insights,
}
PAGE_FUNCS[page]()

st.markdown("---")
st.caption(f"{BANNER} Inspired by DHL colours. Not affiliated with or endorsed by DHL.")
