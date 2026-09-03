"""
modules/dashboard.py
Landing page after login: KPI summary, trend charts, alerts/upcoming.
"""

import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

from database import run_df
from utils import fmt_date, fmt_currency


def _scalar(df, col, default=0):
    if df.empty:
        return default
    v = df.iloc[0][col]
    return default if v is None else v


def _kpi_card(col, label, value, icon, gradient):
    with col:
        st.markdown(
            f"""<div class="kpi-card" style="background:{gradient};">
                    <div class="kpi-icon">{icon}</div>
                    <div class="kpi-label">{label}</div>
                    <div class="kpi-value">{value}</div>
                </div>""",
            unsafe_allow_html=True,
        )


def render(tenant_id, currency_symbol, date_format):
    st.markdown(
        '<div class="sn-section-title">Dashboard</div>'
        '<div class="sn-section-sub">Overview of your business at a glance</div>',
        unsafe_allow_html=True,
    )

    today = datetime.date.today()
    month_start = today.replace(day=1).isoformat()
    today_iso = today.isoformat()

    total_properties = _scalar(run_df("SELECT COUNT(*) AS c FROM properties WHERE tenant_id = ?", (tenant_id,)), "c")
    available_properties = _scalar(run_df(
        "SELECT COUNT(*) AS c FROM properties WHERE tenant_id = ? AND status = 'Available'", (tenant_id,)), "c")
    total_customers = _scalar(run_df("SELECT COUNT(*) AS c FROM customers WHERE tenant_id = ?", (tenant_id,)), "c")
    active_leads = _scalar(run_df(
        "SELECT COUNT(*) AS c FROM leads WHERE tenant_id = ? AND status NOT IN ('Converted','Lost')",
        (tenant_id,)), "c")
    deals_this_month = _scalar(run_df(
        "SELECT COUNT(*) AS c FROM deals WHERE tenant_id = ? AND deal_date >= ?", (tenant_id, month_start)), "c")
    revenue_this_month = _scalar(run_df(
        "SELECT COALESCE(SUM(final_amount),0) AS s FROM deals "
        "WHERE tenant_id = ? AND deal_status = 'Completed' AND deal_date >= ?", (tenant_id, month_start)), "s")
    pending_payments = _scalar(run_df(
        "SELECT COALESCE(SUM(final_amount - booking_amount),0) AS s FROM deals "
        "WHERE tenant_id = ? AND payment_status != 'Paid'", (tenant_id,)), "s")
    upcoming_visits = _scalar(run_df(
        "SELECT COUNT(*) AS c FROM site_visits WHERE tenant_id = ? AND status = 'Scheduled' AND visit_date >= ?",
        (tenant_id, today_iso)), "c")

    cards = [
        ("Total Properties", int(total_properties), "🏢", "linear-gradient(135deg,#4F46E5,#7C3AED)"),
        ("Available Properties", int(available_properties), "✅", "linear-gradient(135deg,#0EA5E9,#0284C7)"),
        ("Total Customers", int(total_customers), "👥", "linear-gradient(135deg,#10B981,#059669)"),
        ("Active Leads", int(active_leads), "🎯", "linear-gradient(135deg,#F59E0B,#D97706)"),
        ("Deals This Month", int(deals_this_month), "🤝", "linear-gradient(135deg,#8B5CF6,#6D28D9)"),
        ("Revenue This Month", fmt_currency(revenue_this_month, currency_symbol), "💰", "linear-gradient(135deg,#14B8A6,#0D9488)"),
        ("Pending Payments", fmt_currency(pending_payments, currency_symbol), "💸", "linear-gradient(135deg,#F97316,#EA580C)"),
        ("Upcoming Site Visits", int(upcoming_visits), "📅", "linear-gradient(135deg,#EF4444,#DC2626)"),
    ]
    cols = st.columns(4) + st.columns(4)
    for i, (label, value, icon, gradient) in enumerate(cards):
        _kpi_card(cols[i], label, value, icon, gradient)

    c1, c2, c3 = st.columns(3)

    with c1:
        st.markdown('<div class="sn-card">', unsafe_allow_html=True)
        st.markdown("**Property Status Breakdown**")
        df = run_df("SELECT status, COUNT(*) AS count FROM properties WHERE tenant_id = ? GROUP BY status", (tenant_id,))
        if df.empty:
            st.caption("No data yet")
        else:
            fig = px.pie(df, names="status", values="count", hole=0.5)
            fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=300)
            st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="sn-card">', unsafe_allow_html=True)
        st.markdown("**Leads by Status**")
        df = run_df("SELECT status, COUNT(*) AS count FROM leads WHERE tenant_id = ? GROUP BY status", (tenant_id,))
        if df.empty:
            st.caption("No data yet")
        else:
            fig = px.bar(df, x="status", y="count", color="status")
            fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=300, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with c3:
        st.markdown('<div class="sn-card">', unsafe_allow_html=True)
        st.markdown("**Revenue Trend (Last 6 Months)**")
        six_months_ago = (today.replace(day=1) - datetime.timedelta(days=160)).replace(day=1).isoformat()
        df = run_df(
            "SELECT deal_date, final_amount FROM deals "
            "WHERE tenant_id = ? AND deal_status = 'Completed' AND deal_date >= ?",
            (tenant_id, six_months_ago),
        )
        if df.empty:
            st.caption("No data yet")
        else:
            df["month"] = pd.to_datetime(df["deal_date"], errors="coerce").dt.strftime("%Y-%m")
            trend = df.groupby("month", as_index=False)["final_amount"].sum().sort_values("month")
            fig = px.line(trend, x="month", y="final_amount", markers=True)
            fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=300)
            st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="sn-card">', unsafe_allow_html=True)
    st.markdown('<div class="sn-section-title" style="font-size:16px;">Alerts &amp; Upcoming</div>', unsafe_allow_html=True)
    a1, a2, a3 = st.columns(3)

    with a1:
        st.markdown("**Upcoming Site Visits**")
        df = run_df(
            "SELECT visit_date, visit_time, assigned_agent FROM site_visits "
            "WHERE tenant_id = ? AND status = 'Scheduled' AND visit_date >= ? ORDER BY visit_date ASC LIMIT 5",
            (tenant_id, today_iso),
        )
        if df.empty:
            st.caption("No upcoming visits")
        else:
            df["visit_date"] = df["visit_date"].apply(lambda v: fmt_date(v, date_format))
            st.dataframe(df, use_container_width=True, hide_index=True)

    with a2:
        st.markdown("**Due / Overdue Follow-ups**")
        cutoff = (today + datetime.timedelta(days=3)).isoformat()
        df = run_df(
            "SELECT lead_name, assigned_agent, next_followup_date FROM leads "
            "WHERE tenant_id = ? AND status NOT IN ('Converted','Lost') AND next_followup_date IS NOT NULL "
            "AND next_followup_date <= ? ORDER BY next_followup_date ASC LIMIT 5",
            (tenant_id, cutoff),
        )
        if df.empty:
            st.caption("No follow-ups due")
        else:
            df["next_followup_date"] = df["next_followup_date"].apply(lambda v: fmt_date(v, date_format))
            st.dataframe(df, use_container_width=True, hide_index=True)

    with a3:
        st.markdown("**Deals Stuck in Negotiation**")
        stale_cutoff = (today - datetime.timedelta(days=14)).isoformat()
        df = run_df(
            "SELECT agent, deal_date, final_amount FROM deals "
            "WHERE tenant_id = ? AND deal_status = 'Negotiation' AND deal_date <= ? ORDER BY deal_date ASC LIMIT 5",
            (tenant_id, stale_cutoff),
        )
        if df.empty:
            st.caption("No stuck deals")
        else:
            df["deal_date"] = df["deal_date"].apply(lambda v: fmt_date(v, date_format))
            df["final_amount"] = df["final_amount"].apply(lambda v: fmt_currency(v, currency_symbol))
            st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown('</div>', unsafe_allow_html=True)
