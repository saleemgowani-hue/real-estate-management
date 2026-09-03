"""
modules/site_visits.py
Site visit scheduling: add/search/edit/delete visits (joined with customer
and property names), feedback capture, Excel/PDF export.
"""

import datetime

import streamlit as st

from config import VISIT_STATUSES
from database import run_query, run_df, log_activity
from utils import today_str, fmt_date, is_blank, dataframe_to_excel_bytes, dataframe_to_pdf_bytes
from style import badge_html

DATE_RANGE_OPTIONS = ["All", "Upcoming", "Today", "Past"]


def render(tenant_id, currency_symbol, date_format):
    st.markdown(
        '<div class="sn-section-title">📅 Site Visits</div>'
        '<div class="sn-section-sub">Schedule and track property site visits.</div>',
        unsafe_allow_html=True,
    )

    tab_add, tab_manage = st.tabs(["➕ Schedule Visit", "📋 Manage Visits"])

    with tab_add:
        _render_add_form(tenant_id)

    with tab_manage:
        _render_manage(tenant_id, date_format)


def _load_customers(tenant_id):
    return run_df("SELECT id, name FROM customers WHERE tenant_id = ?", (tenant_id,))


def _load_properties(tenant_id):
    return run_df("SELECT id, property_name FROM properties WHERE tenant_id = ?", (tenant_id,))


def _render_add_form(tenant_id):
    st.markdown('<div class="sn-card">', unsafe_allow_html=True)

    customers_df = _load_customers(tenant_id)
    properties_df = _load_properties(tenant_id)

    if customers_df.empty or properties_df.empty:
        st.warning("Add at least one customer and one property before scheduling a site visit.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    customer_options = {f"{r.id} — {r.name}": r.id for r in customers_df.itertuples()}
    property_options = {f"{r.id} — {r.property_name}": r.id for r in properties_df.itertuples()}

    with st.form("add_visit_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            customer_label = st.selectbox("Customer", list(customer_options.keys()))
            visit_date = st.date_input("Visit Date", value=datetime.date.today())
            assigned_agent = st.text_input("Assigned Agent")
        with c2:
            property_label = st.selectbox("Property", list(property_options.keys()))
            visit_time = st.time_input("Visit Time", value=datetime.time(11, 0))
            status = st.selectbox("Status", VISIT_STATUSES)

        remarks = st.text_area("Remarks")
        feedback = st.text_area("Feedback")

        submitted = st.form_submit_button("Schedule Visit", type="primary", use_container_width=True)

    if submitted:
        run_query(
            """INSERT INTO site_visits (tenant_id, customer_id, property_id, visit_date, visit_time,
                assigned_agent, status, feedback, remarks) VALUES (?,?,?,?,?,?,?,?,?)""",
            (tenant_id, customer_options[customer_label], property_options[property_label], str(visit_date),
             visit_time.strftime("%H:%M"), assigned_agent, status, feedback, remarks),
        )
        log_activity(tenant_id, "Site Visit Scheduled", f"Scheduled visit for '{customer_label}' at '{property_label}'")
        st.success("Site visit scheduled successfully.")
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


def _render_manage(tenant_id, date_format):
    st.markdown('<div class="sn-card">', unsafe_allow_html=True)

    c1, c2 = st.columns([1, 1])
    with c1:
        f_status = st.selectbox("Status", ["All"] + VISIT_STATUSES)
    with c2:
        f_range = st.selectbox("Date Range", DATE_RANGE_OPTIONS)

    sql = """SELECT sv.*, c.name AS customer_name, p.property_name FROM site_visits sv
              LEFT JOIN customers c ON sv.customer_id = c.id
              LEFT JOIN properties p ON sv.property_id = p.id
              WHERE sv.tenant_id = ?"""
    params = [tenant_id]
    if f_status != "All":
        sql += " AND sv.status = ?"
        params.append(f_status)

    today = datetime.date.today().isoformat()
    if f_range == "Upcoming":
        sql += " AND sv.visit_date > ?"
        params.append(today)
    elif f_range == "Today":
        sql += " AND sv.visit_date = ?"
        params.append(today)
    elif f_range == "Past":
        sql += " AND sv.visit_date < ?"
        params.append(today)

    sql += " ORDER BY sv.visit_date DESC, sv.id DESC"

    df = run_df(sql, tuple(params))

    if df.empty:
        st.info("No site visits found.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    display_df = df.copy()
    display_df["visit_date_display"] = display_df["visit_date"].apply(lambda v: fmt_date(v, date_format))

    st.dataframe(
        display_df[["id", "customer_name", "property_name", "visit_date_display", "visit_time",
                    "assigned_agent", "status"]].rename(columns={
            "customer_name": "Customer", "property_name": "Property", "visit_date_display": "Date",
            "visit_time": "Time", "assigned_agent": "Agent", "status": "Status",
        }),
        use_container_width=True, hide_index=True,
    )

    ce1, ce2 = st.columns(2)
    with ce1:
        st.download_button(
            "⬇️ Export Excel", dataframe_to_excel_bytes(display_df[[
                "customer_name", "property_name", "visit_date", "visit_time", "assigned_agent", "status"]],
                "Site Visits", "Site Visits Report"),
            file_name="site_visits.xlsx", use_container_width=True,
        )
    with ce2:
        st.download_button(
            "⬇️ Export PDF", dataframe_to_pdf_bytes(display_df[[
                "customer_name", "property_name", "visit_date", "visit_time", "assigned_agent", "status"]],
                "Site Visits Report"),
            file_name="site_visits.pdf", use_container_width=True,
        )

    st.markdown("---")
    options = {f"{row.id} — {row.customer_name} @ {row.property_name} ({row.visit_date})": row.id for row in df.itertuples()}
    selected_label = st.selectbox("Select a visit to view / edit / delete", list(options.keys()))
    selected_id = options[selected_label]
    _render_detail(tenant_id, selected_id, date_format)

    st.markdown('</div>', unsafe_allow_html=True)


def _render_detail(tenant_id, visit_id, date_format):
    row = run_query(
        """SELECT sv.*, c.name AS customer_name, p.property_name FROM site_visits sv
           LEFT JOIN customers c ON sv.customer_id = c.id
           LEFT JOIN properties p ON sv.property_id = p.id
           WHERE sv.id = ? AND sv.tenant_id = ?""",
        (visit_id, tenant_id), fetchone=True,
    )
    if not row:
        st.warning("Site visit not found.")
        return

    st.markdown(f"#### {row['customer_name']} @ {row['property_name']}  {badge_html(row['status'])}", unsafe_allow_html=True)
    dc1, dc2 = st.columns(2)
    with dc1:
        st.write(f"**Date:** {fmt_date(row['visit_date'], date_format)} at {row['visit_time']}")
        st.write(f"**Agent:** {row['assigned_agent']}")
    with dc2:
        st.write(f"**Feedback:** {row['feedback'] or '-'}")
        st.write(f"**Remarks:** {row['remarks'] or '-'}")

    st.markdown("---")
    tab_edit, tab_delete = st.tabs(["✏️ Edit / Feedback", "🗑️ Delete"])

    with tab_edit:
        customers_df = _load_customers(tenant_id)
        properties_df = _load_properties(tenant_id)
        customer_options = {f"{r.id} — {r.name}": r.id for r in customers_df.itertuples()}
        property_options = {f"{r.id} — {r.property_name}": r.id for r in properties_df.itertuples()}

        cur_customer_label = next((k for k, v in customer_options.items() if v == row["customer_id"]), None)
        cur_property_label = next((k for k, v in property_options.items() if v == row["property_id"]), None)
        cust_labels = list(customer_options.keys())
        prop_labels = list(property_options.keys())

        with st.form(f"edit_visit_{visit_id}"):
            e1, e2 = st.columns(2)
            with e1:
                customer_label = st.selectbox(
                    "Customer", cust_labels,
                    index=cust_labels.index(cur_customer_label) if cur_customer_label in cust_labels else 0,
                )
                try:
                    current_date = datetime.date.fromisoformat(str(row["visit_date"])[:10])
                except (ValueError, TypeError):
                    current_date = datetime.date.today()
                visit_date = st.date_input("Visit Date", value=current_date)
                assigned_agent = st.text_input("Assigned Agent", value=row["assigned_agent"] or "")
            with e2:
                property_label = st.selectbox(
                    "Property", prop_labels,
                    index=prop_labels.index(cur_property_label) if cur_property_label in prop_labels else 0,
                )
                try:
                    current_time = datetime.datetime.strptime(str(row["visit_time"]), "%H:%M").time()
                except (ValueError, TypeError):
                    current_time = datetime.time(11, 0)
                visit_time = st.time_input("Visit Time", value=current_time)
                status = st.selectbox("Status", VISIT_STATUSES, index=_safe_index(VISIT_STATUSES, row["status"]))

            remarks = st.text_area("Remarks", value=row["remarks"] or "")
            feedback = st.text_area("Feedback", value=row["feedback"] or "")

            update_submitted = st.form_submit_button("Update Visit", type="primary", use_container_width=True)

        if update_submitted:
            run_query(
                """UPDATE site_visits SET customer_id=?, property_id=?, visit_date=?, visit_time=?,
                   assigned_agent=?, status=?, feedback=?, remarks=? WHERE id = ? AND tenant_id = ?""",
                (customer_options[customer_label], property_options[property_label], str(visit_date),
                 visit_time.strftime("%H:%M"), assigned_agent, status, feedback, remarks, visit_id, tenant_id),
            )
            log_activity(tenant_id, "Site Visit Updated", f"Updated visit #{visit_id}")
            st.success("Site visit updated.")
            st.rerun()

    with tab_delete:
        st.warning("This will permanently delete this site visit.")
        confirm = st.checkbox("I confirm I want to delete this visit", key=f"confirm_del_visit_{visit_id}")
        if st.button("Delete Visit", key=f"del_visit_{visit_id}", disabled=not confirm):
            run_query("DELETE FROM site_visits WHERE id = ? AND tenant_id = ?", (visit_id, tenant_id))
            log_activity(tenant_id, "Site Visit Deleted", f"Deleted visit #{visit_id}")
            st.success("Site visit deleted.")
            st.rerun()


def _safe_index(options, value):
    try:
        return options.index(value)
    except (ValueError, TypeError):
        return 0
