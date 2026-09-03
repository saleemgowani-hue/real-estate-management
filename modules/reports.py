"""
modules/reports.py
Reports Hub: pick a report type, filter it, view it, export it (Excel/PDF).
"""

import datetime

import pandas as pd
import streamlit as st

from database import run_df
from config import (
    APP_NAME, PROPERTY_TYPES, PROPERTY_STATUSES, LEAD_STATUSES, LEAD_SOURCES,
    VISIT_STATUSES, DEAL_STATUSES, PAYMENT_STATUSES, PAYMENT_MODES,
    EXPENSE_CATEGORIES, STAFF_ROLES,
)
from utils import fmt_date, fmt_currency, date_range_for_filter, dataframe_to_excel_bytes, dataframe_to_pdf_bytes

DATE_RANGE_OPTIONS = ["Today", "This Week", "This Month", "Last Month", "This Year", "Custom", "All Time"]


def _date_filter(key, default_index=2):
    choice = st.selectbox("Date Range", DATE_RANGE_OPTIONS, index=default_index, key=f"{key}_range")
    if choice == "Custom":
        c1, c2 = st.columns(2)
        with c1:
            start = st.date_input("From", value=datetime.date.today().replace(day=1), key=f"{key}_from")
        with c2:
            end = st.date_input("To", value=datetime.date.today(), key=f"{key}_to")
        return start, end
    if choice == "All Time":
        return None, None
    return date_range_for_filter(choice)


def _with_date_filter(sql, params, column, start, end):
    if start and end:
        sql += f" AND {column} BETWEEN ? AND ?"
        params = params + (start.isoformat(), end.isoformat())
    return sql, params


def _properties_report(tenant_id, currency_symbol, date_format):
    c1, c2 = st.columns(2)
    with c1:
        start, end = _date_filter("prop")
    with c2:
        status = st.selectbox("Status", ["All"] + PROPERTY_STATUSES, key="prop_status")
    sql = ("SELECT property_name, property_type, listing_type, city, locality, price, rent_amount, "
           "status, date_added FROM properties WHERE tenant_id = ?")
    params = (tenant_id,)
    sql, params = _with_date_filter(sql, params, "date_added", start, end)
    if status != "All":
        sql += " AND status = ?"
        params += (status,)
    sql += " ORDER BY date_added DESC"
    df = run_df(sql, params)
    if not df.empty:
        df["date_added"] = df["date_added"].apply(lambda v: fmt_date(v, date_format))
        df["price"] = df["price"].apply(lambda v: fmt_currency(v, currency_symbol))
        df["rent_amount"] = df["rent_amount"].apply(lambda v: fmt_currency(v, currency_symbol))
    return df, "Properties Report", "Properties"


def _customers_report(tenant_id, currency_symbol, date_format):
    c1, c2 = st.columns(2)
    with c1:
        start, end = _date_filter("cust")
    with c2:
        source = st.selectbox("Source", ["All"] + LEAD_SOURCES, key="cust_source")
    sql = ("SELECT name, mobile, email, preferred_location, budget, property_type_required, "
           "buy_or_rent, source, assigned_agent, date_added FROM customers WHERE tenant_id = ?")
    params = (tenant_id,)
    sql, params = _with_date_filter(sql, params, "date_added", start, end)
    if source != "All":
        sql += " AND source = ?"
        params += (source,)
    sql += " ORDER BY date_added DESC"
    df = run_df(sql, params)
    if not df.empty:
        df["date_added"] = df["date_added"].apply(lambda v: fmt_date(v, date_format))
        df["budget"] = df["budget"].apply(lambda v: fmt_currency(v, currency_symbol))
    return df, "Customers Report", "Customers"


def _leads_report(tenant_id, currency_symbol, date_format):
    c1, c2 = st.columns(2)
    with c1:
        start, end = _date_filter("lead")
    with c2:
        status = st.selectbox("Status", ["All"] + LEAD_STATUSES, key="lead_status")
    sql = ("SELECT lead_name, mobile, requirement, budget, preferred_location, property_type, source, "
           "assigned_agent, status, next_followup_date, date_added FROM leads WHERE tenant_id = ?")
    params = (tenant_id,)
    sql, params = _with_date_filter(sql, params, "date_added", start, end)
    if status != "All":
        sql += " AND status = ?"
        params += (status,)
    sql += " ORDER BY date_added DESC"
    df = run_df(sql, params)
    if not df.empty:
        df["date_added"] = df["date_added"].apply(lambda v: fmt_date(v, date_format))
        df["next_followup_date"] = df["next_followup_date"].apply(lambda v: fmt_date(v, date_format))
        df["budget"] = df["budget"].apply(lambda v: fmt_currency(v, currency_symbol))
    return df, "Leads Report", "Leads"


def _site_visits_report(tenant_id, currency_symbol, date_format):
    c1, c2 = st.columns(2)
    with c1:
        start, end = _date_filter("visit")
    with c2:
        status = st.selectbox("Status", ["All"] + VISIT_STATUSES, key="visit_status")
    sql = ("SELECT sv.visit_date, sv.visit_time, c.name AS customer_name, p.property_name, "
           "sv.assigned_agent, sv.status, sv.feedback FROM site_visits sv "
           "LEFT JOIN customers c ON c.id = sv.customer_id "
           "LEFT JOIN properties p ON p.id = sv.property_id WHERE sv.tenant_id = ?")
    params = (tenant_id,)
    sql, params = _with_date_filter(sql, params, "sv.visit_date", start, end)
    if status != "All":
        sql += " AND sv.status = ?"
        params += (status,)
    sql += " ORDER BY sv.visit_date DESC"
    df = run_df(sql, params)
    if not df.empty:
        df["visit_date"] = df["visit_date"].apply(lambda v: fmt_date(v, date_format))
    return df, "Site Visits Report", "SiteVisits"


def _deals_report(tenant_id, currency_symbol, date_format):
    c1, c2 = st.columns(2)
    with c1:
        start, end = _date_filter("deal")
    with c2:
        status = st.selectbox("Deal Status", ["All"] + DEAL_STATUSES, key="deal_status")
    sql = ("SELECT d.deal_date, c.name AS customer_name, p.property_name, d.agent, d.property_value, "
           "d.discount, d.final_amount, d.booking_amount, d.commission, d.payment_status, d.deal_status "
           "FROM deals d LEFT JOIN customers c ON c.id = d.customer_id "
           "LEFT JOIN properties p ON p.id = d.property_id WHERE d.tenant_id = ?")
    params = (tenant_id,)
    sql, params = _with_date_filter(sql, params, "d.deal_date", start, end)
    if status != "All":
        sql += " AND d.deal_status = ?"
        params += (status,)
    sql += " ORDER BY d.deal_date DESC"
    df = run_df(sql, params)
    if not df.empty:
        df["deal_date"] = df["deal_date"].apply(lambda v: fmt_date(v, date_format))
        for col in ("property_value", "discount", "final_amount", "booking_amount", "commission"):
            df[col] = df[col].apply(lambda v: fmt_currency(v, currency_symbol))
    return df, "Deals Report", "Deals"


def _payments_report(tenant_id, currency_symbol, date_format):
    c1, c2 = st.columns(2)
    with c1:
        start, end = _date_filter("pay")
    with c2:
        mode = st.selectbox("Payment Mode", ["All"] + PAYMENT_MODES, key="pay_mode")
    sql = ("SELECT p.payment_date, c.name AS customer_name, pr.property_name, p.amount, "
           "p.payment_mode, p.transaction_number FROM payments p "
           "LEFT JOIN customers c ON c.id = p.customer_id "
           "LEFT JOIN properties pr ON pr.id = p.property_id WHERE p.tenant_id = ?")
    params = (tenant_id,)
    sql, params = _with_date_filter(sql, params, "p.payment_date", start, end)
    if mode != "All":
        sql += " AND p.payment_mode = ?"
        params += (mode,)
    sql += " ORDER BY p.payment_date DESC"
    df = run_df(sql, params)
    if not df.empty:
        df["payment_date"] = df["payment_date"].apply(lambda v: fmt_date(v, date_format))
        df["amount"] = df["amount"].apply(lambda v: fmt_currency(v, currency_symbol))
    return df, "Payments Report", "Payments"


def _expenses_report(tenant_id, currency_symbol, date_format):
    c1, c2 = st.columns(2)
    with c1:
        start, end = _date_filter("exp")
    with c2:
        category = st.selectbox("Category", ["All"] + EXPENSE_CATEGORIES, key="exp_category")
    sql = ("SELECT expense_date, category, description, amount, payment_mode, paid_by "
           "FROM expenses WHERE tenant_id = ?")
    params = (tenant_id,)
    sql, params = _with_date_filter(sql, params, "expense_date", start, end)
    if category != "All":
        sql += " AND category = ?"
        params += (category,)
    sql += " ORDER BY expense_date DESC"
    df = run_df(sql, params)
    if not df.empty:
        df["expense_date"] = df["expense_date"].apply(lambda v: fmt_date(v, date_format))
        df["amount"] = df["amount"].apply(lambda v: fmt_currency(v, currency_symbol))
    return df, "Expenses Report", "Expenses"


def _staff_report(tenant_id, currency_symbol, date_format):
    c1, c2 = st.columns(2)
    with c1:
        start, end = _date_filter("staff", default_index=6)
    with c2:
        role = st.selectbox("Role", ["All"] + STAFF_ROLES, key="staff_role")
    sql = ("SELECT name, mobile, email, role, joining_date, salary, commission_percent, status "
           "FROM staff WHERE tenant_id = ?")
    params = (tenant_id,)
    sql, params = _with_date_filter(sql, params, "joining_date", start, end)
    if role != "All":
        sql += " AND role = ?"
        params += (role,)
    sql += " ORDER BY joining_date DESC"
    df = run_df(sql, params)
    if not df.empty:
        df["joining_date"] = df["joining_date"].apply(lambda v: fmt_date(v, date_format))
        df["salary"] = df["salary"].apply(lambda v: fmt_currency(v, currency_symbol))
    return df, "Staff Report", "Staff"


def _revenue_summary_report(tenant_id, currency_symbol, date_format):
    start, end = _date_filter("revsum")
    sql = "SELECT deal_date, final_amount FROM deals WHERE tenant_id = ? AND deal_status = 'Completed'"
    params = (tenant_id,)
    sql, params = _with_date_filter(sql, params, "deal_date", start, end)
    raw = run_df(sql, params)
    if raw.empty:
        return raw, "Revenue Summary Report", "RevenueSummary"
    raw["month"] = pd.to_datetime(raw["deal_date"], errors="coerce").dt.strftime("%Y-%m")
    summary = raw.groupby("month", as_index=False).agg(deals_closed=("final_amount", "count"),
                                                         total_revenue=("final_amount", "sum"))
    summary = summary.sort_values("month")
    summary["total_revenue"] = summary["total_revenue"].apply(lambda v: fmt_currency(v, currency_symbol))
    return summary, "Revenue Summary Report", "RevenueSummary"


def _outstanding_payments_report(tenant_id, currency_symbol, date_format):
    start, end = _date_filter("outstanding")
    sql = ("SELECT d.deal_date, c.name AS customer_name, p.property_name, d.agent, d.final_amount, "
           "d.booking_amount, (COALESCE(d.final_amount,0) - COALESCE(d.booking_amount,0)) AS outstanding_amount, "
           "d.payment_status FROM deals d LEFT JOIN customers c ON c.id = d.customer_id "
           "LEFT JOIN properties p ON p.id = d.property_id "
           "WHERE d.tenant_id = ? AND d.payment_status != 'Paid'")
    params = (tenant_id,)
    sql, params = _with_date_filter(sql, params, "d.deal_date", start, end)
    sql += " ORDER BY outstanding_amount DESC"
    df = run_df(sql, params)
    if not df.empty:
        df["deal_date"] = df["deal_date"].apply(lambda v: fmt_date(v, date_format))
        for col in ("final_amount", "booking_amount", "outstanding_amount"):
            df[col] = df[col].apply(lambda v: fmt_currency(v, currency_symbol))
    return df, "Outstanding Payments Report", "OutstandingPayments"


def _lead_source_analysis_report(tenant_id, currency_symbol, date_format):
    start, end = _date_filter("source")
    sql = "SELECT source, status FROM leads WHERE tenant_id = ?"
    params = (tenant_id,)
    sql, params = _with_date_filter(sql, params, "date_added", start, end)
    raw = run_df(sql, params)
    if raw.empty:
        return raw, "Lead Source Analysis Report", "LeadSourceAnalysis"
    raw["source"] = raw["source"].fillna("Unknown")
    grouped = raw.groupby("source").agg(
        total_leads=("status", "count"),
        converted=("status", lambda s: (s == "Converted").sum()),
    ).reset_index()
    grouped["conversion_rate"] = grouped.apply(
        lambda r: f"{(r['converted'] / r['total_leads'] * 100):.1f}%" if r["total_leads"] else "0.0%", axis=1)
    grouped = grouped.sort_values("total_leads", ascending=False)
    return grouped, "Lead Source Analysis Report", "LeadSourceAnalysis"


def _agent_performance_report(tenant_id, currency_symbol, date_format):
    start, end = _date_filter("agentperf")
    sql = "SELECT agent, final_amount FROM deals WHERE tenant_id = ? AND deal_status = 'Completed' AND agent IS NOT NULL"
    params = (tenant_id,)
    sql, params = _with_date_filter(sql, params, "deal_date", start, end)
    raw = run_df(sql, params)
    if raw.empty:
        return raw, "Agent Performance Report", "AgentPerformance"
    grouped = raw.groupby("agent", as_index=False).agg(deals_closed=("final_amount", "count"),
                                                         total_revenue=("final_amount", "sum"),
                                                         avg_deal_size=("final_amount", "mean"))
    grouped = grouped.sort_values("total_revenue", ascending=False)
    grouped["total_revenue"] = grouped["total_revenue"].apply(lambda v: fmt_currency(v, currency_symbol))
    grouped["avg_deal_size"] = grouped["avg_deal_size"].apply(lambda v: fmt_currency(v, currency_symbol))
    return grouped, "Agent Performance Report", "AgentPerformance"


def _property_status_report(tenant_id, currency_symbol, date_format):
    c1, c2 = st.columns(2)
    with c1:
        start, end = _date_filter("propstatus", default_index=6)
    with c2:
        ptype = st.selectbox("Property Type", ["All"] + PROPERTY_TYPES, key="propstatus_type")
    sql = "SELECT status, price FROM properties WHERE tenant_id = ?"
    params = (tenant_id,)
    sql, params = _with_date_filter(sql, params, "date_added", start, end)
    if ptype != "All":
        sql += " AND property_type = ?"
        params += (ptype,)
    raw = run_df(sql, params)
    if raw.empty:
        return raw, "Property Status Report", "PropertyStatus"
    grouped = raw.groupby("status", as_index=False).agg(count=("price", "count"), total_value=("price", "sum"))
    grouped["total_value"] = grouped["total_value"].apply(lambda v: fmt_currency(v, currency_symbol))
    grouped = grouped.sort_values("count", ascending=False)
    return grouped, "Property Status Report", "PropertyStatus"


def _followups_report(tenant_id, currency_symbol, date_format):
    c1, c2 = st.columns(2)
    with c1:
        start, end = _date_filter("followup")
    with c2:
        done_filter = st.selectbox("Status", ["All", "Pending", "Done"], key="followup_done")
    sql = ("SELECT f.followup_date, l.lead_name, c.name AS customer_name, f.note, f.is_done "
           "FROM followups f LEFT JOIN leads l ON l.id = f.lead_id "
           "LEFT JOIN customers c ON c.id = f.customer_id WHERE f.tenant_id = ?")
    params = (tenant_id,)
    sql, params = _with_date_filter(sql, params, "f.followup_date", start, end)
    if done_filter == "Pending":
        sql += " AND f.is_done = 0"
    elif done_filter == "Done":
        sql += " AND f.is_done = 1"
    sql += " ORDER BY f.followup_date DESC"
    df = run_df(sql, params)
    if not df.empty:
        df["followup_date"] = df["followup_date"].apply(lambda v: fmt_date(v, date_format))
        df["is_done"] = df["is_done"].apply(lambda v: "Done" if v in (1, True, "1") else "Pending")
    return df, "Follow-ups Report", "Followups"


REPORTS = {
    "Properties Report": _properties_report,
    "Customers Report": _customers_report,
    "Leads Report": _leads_report,
    "Site Visits Report": _site_visits_report,
    "Deals Report": _deals_report,
    "Payments Report": _payments_report,
    "Expenses Report": _expenses_report,
    "Staff Report": _staff_report,
    "Revenue Summary Report": _revenue_summary_report,
    "Outstanding Payments Report": _outstanding_payments_report,
    "Lead Source Analysis Report": _lead_source_analysis_report,
    "Agent Performance Report": _agent_performance_report,
    "Property Status Report": _property_status_report,
    "Follow-ups Report": _followups_report,
}


def render(tenant_id, currency_symbol, date_format):
    st.markdown(
        '<div class="sn-section-title">Reports Hub</div>'
        '<div class="sn-section-sub">Generate, filter and export business reports</div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="sn-card">', unsafe_allow_html=True)
    report_name = st.selectbox("Select Report", list(REPORTS.keys()), key="report_select")
    df, title, sheet = REPORTS[report_name](tenant_id, currency_symbol, date_format)

    st.markdown("---")
    st.dataframe(df, use_container_width=True, hide_index=True)

    file_stub = sheet.lower()
    c1, c2 = st.columns(2)
    with c1:
        st.download_button(
            "⬇️ Download Excel",
            data=dataframe_to_excel_bytes(df, sheet_name=sheet, title=title),
            file_name=f"{file_stub}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    with c2:
        st.download_button(
            "⬇️ Download PDF",
            data=dataframe_to_pdf_bytes(df, title=title, company_name=APP_NAME),
            file_name=f"{file_stub}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    st.markdown('</div>', unsafe_allow_html=True)
