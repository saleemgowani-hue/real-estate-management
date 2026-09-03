"""
modules/kpi_analytics.py
Deeper analytics than the dashboard: agent performance, lead conversion
funnel, property performance, revenue trend, expense breakdown.
"""

import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from database import run_df
from config import LEAD_STATUSES
from utils import fmt_currency


def render(tenant_id, currency_symbol, date_format):
    st.markdown(
        '<div class="sn-section-title">KPI Analytics</div>'
        '<div class="sn-section-sub">Performance insights across agents, leads, properties and revenue</div>',
        unsafe_allow_html=True,
    )

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["Agent Performance", "Lead Funnel", "Property Performance", "Revenue Trend", "Expenses"]
    )

    with tab1:
        _agent_performance(tenant_id, currency_symbol)
    with tab2:
        _lead_funnel(tenant_id)
    with tab3:
        _property_performance(tenant_id, currency_symbol)
    with tab4:
        _revenue_trend(tenant_id, currency_symbol)
    with tab5:
        _expense_breakdown(tenant_id)


def _agent_performance(tenant_id, currency_symbol):
    st.markdown("**Deals Closed & Revenue by Agent**")
    df = run_df(
        "SELECT agent, COUNT(*) AS deals_closed, COALESCE(SUM(final_amount),0) AS revenue "
        "FROM deals WHERE tenant_id = ? AND deal_status = 'Completed' AND agent IS NOT NULL "
        "GROUP BY agent ORDER BY revenue DESC",
        (tenant_id,),
    )
    if df.empty:
        st.info("No completed deals yet.")
        return
    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(df, x="agent", y="deals_closed", color="agent", title="Deals Closed")
        fig.update_layout(showlegend=False, height=360)
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig = px.bar(df, x="agent", y="revenue", color="agent", title="Revenue")
        fig.update_layout(showlegend=False, height=360)
        st.plotly_chart(fig, use_container_width=True)
    display_df = df.copy()
    display_df["revenue"] = display_df["revenue"].apply(lambda v: fmt_currency(v, currency_symbol))
    st.dataframe(display_df, use_container_width=True, hide_index=True)


def _lead_funnel(tenant_id):
    st.markdown("**Lead Conversion Funnel**")
    df = run_df("SELECT status, COUNT(*) AS count FROM leads WHERE tenant_id = ? GROUP BY status", (tenant_id,))
    if df.empty:
        st.info("No leads yet.")
        return
    counts = {s: 0 for s in LEAD_STATUSES}
    for _, row in df.iterrows():
        if row["status"] in counts:
            counts[row["status"]] = row["count"]
    total = sum(counts.values())
    converted = counts.get("Converted", 0)
    rate = (converted / total * 100) if total else 0

    fig = go.Figure(go.Funnel(y=LEAD_STATUSES, x=[counts[s] for s in LEAD_STATUSES]))
    fig.update_layout(height=420, margin=dict(t=20, b=20))
    st.plotly_chart(fig, use_container_width=True)
    st.metric("Overall Conversion Rate", f"{rate:.1f}%", help="Converted leads / total leads")


def _property_performance(tenant_id, currency_symbol):
    st.markdown("**Property Performance**")
    c1, c2 = st.columns(2)
    with c1:
        df = run_df(
            "SELECT property_type, COUNT(*) AS count FROM properties "
            "WHERE tenant_id = ? AND property_type IS NOT NULL GROUP BY property_type",
            (tenant_id,),
        )
        if df.empty:
            st.caption("No property data yet")
        else:
            fig = px.bar(df, x="property_type", y="count", title="Count by Property Type", color="property_type")
            fig.update_layout(showlegend=False, height=340)
            st.plotly_chart(fig, use_container_width=True)
    with c2:
        df2 = run_df(
            "SELECT city, COALESCE(AVG(price),0) AS avg_price FROM properties "
            "WHERE tenant_id = ? AND city IS NOT NULL GROUP BY city",
            (tenant_id,),
        )
        if df2.empty:
            st.caption("No property data yet")
        else:
            fig = px.bar(df2, x="city", y="avg_price", title="Average Price by City", color="city")
            fig.update_layout(showlegend=False, height=340)
            st.plotly_chart(fig, use_container_width=True)

    df3 = run_df(
        "SELECT listing_type, COUNT(*) AS count FROM properties "
        "WHERE tenant_id = ? AND listing_type IS NOT NULL GROUP BY listing_type",
        (tenant_id,),
    )
    if not df3.empty:
        fig = px.pie(df3, names="listing_type", values="count", title="Sale vs Rent Listings", hole=0.5)
        fig.update_layout(height=340)
        st.plotly_chart(fig, use_container_width=True)


def _revenue_trend(tenant_id, currency_symbol):
    st.markdown("**Monthly Revenue Trend (Last 12 Months)**")
    cutoff = (datetime.date.today().replace(day=1) - datetime.timedelta(days=365)).isoformat()
    df = run_df(
        "SELECT deal_date, final_amount FROM deals "
        "WHERE tenant_id = ? AND deal_status = 'Completed' AND deal_date >= ?",
        (tenant_id, cutoff),
    )
    if df.empty:
        st.info("No completed deals in this period.")
        return
    df["month"] = pd.to_datetime(df["deal_date"], errors="coerce").dt.strftime("%Y-%m")
    trend = df.groupby("month", as_index=False)["final_amount"].sum().sort_values("month")
    fig = px.line(trend, x="month", y="final_amount", markers=True)
    fig.update_layout(height=380)
    st.plotly_chart(fig, use_container_width=True)

    if len(trend) >= 2:
        current = trend.iloc[-1]["final_amount"]
        previous = trend.iloc[-2]["final_amount"]
        pct = ((current - previous) / previous * 100) if previous else 0
        st.metric("This Month vs Last Month", fmt_currency(current, currency_symbol), f"{pct:+.1f}%")


def _expense_breakdown(tenant_id):
    st.markdown("**Expense Breakdown**")
    c1, c2 = st.columns(2)
    with c1:
        df = run_df(
            "SELECT category, COALESCE(SUM(amount),0) AS total FROM expenses WHERE tenant_id = ? GROUP BY category",
            (tenant_id,),
        )
        if df.empty:
            st.caption("No expenses recorded yet")
        else:
            fig = px.pie(df, names="category", values="total", hole=0.5, title="By Category")
            fig.update_layout(height=360)
            st.plotly_chart(fig, use_container_width=True)
    with c2:
        cutoff = (datetime.date.today().replace(day=1) - datetime.timedelta(days=365)).isoformat()
        exp_df = run_df(
            "SELECT expense_date AS d, amount FROM expenses WHERE tenant_id = ? AND expense_date >= ?",
            (tenant_id, cutoff),
        )
        rev_df = run_df(
            "SELECT deal_date AS d, final_amount AS amount FROM deals "
            "WHERE tenant_id = ? AND deal_status = 'Completed' AND deal_date >= ?",
            (tenant_id, cutoff),
        )
        if exp_df.empty and rev_df.empty:
            st.caption("No data yet")
        else:
            exp_df["month"] = pd.to_datetime(exp_df["d"], errors="coerce").dt.strftime("%Y-%m")
            rev_df["month"] = pd.to_datetime(rev_df["d"], errors="coerce").dt.strftime("%Y-%m")
            exp_m = exp_df.groupby("month", as_index=False)["amount"].sum().rename(columns={"amount": "Expenses"})
            rev_m = rev_df.groupby("month", as_index=False)["amount"].sum().rename(columns={"amount": "Revenue"})
            merged = pd.merge(rev_m, exp_m, on="month", how="outer").fillna(0).sort_values("month")
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=merged["month"], y=merged["Revenue"], name="Revenue", mode="lines+markers"))
            fig.add_trace(go.Scatter(x=merged["month"], y=merged["Expenses"], name="Expenses", mode="lines+markers"))
            fig.update_layout(height=360, title="Revenue vs Expenses")
            st.plotly_chart(fig, use_container_width=True)
