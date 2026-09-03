"""
modules/leads.py
Leads / CRM: add/search/edit/delete leads, overdue follow-up highlighting,
convert-to-customer, Excel/PDF export.
"""

import datetime

import streamlit as st

from config import LEAD_STATUSES, LEAD_SOURCES, PROPERTY_TYPES
from database import run_query, run_df, log_activity
from utils import today_str, fmt_date, fmt_currency, safe_float, is_blank, dataframe_to_excel_bytes, dataframe_to_pdf_bytes
from style import badge_html


def render(tenant_id, currency_symbol, date_format):
    st.markdown(
        '<div class="sn-section-title">🎯 Leads / CRM</div>'
        '<div class="sn-section-sub">Track leads, follow-ups, and convert them into customers.</div>',
        unsafe_allow_html=True,
    )

    tab_add, tab_manage = st.tabs(["➕ Add Lead", "📋 Manage Leads"])

    with tab_add:
        _render_add_form(tenant_id)

    with tab_manage:
        _render_manage(tenant_id, currency_symbol, date_format)


def _render_add_form(tenant_id):
    st.markdown('<div class="sn-card">', unsafe_allow_html=True)
    with st.form("add_lead_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            lead_name = st.text_input("Lead Name *")
            mobile = st.text_input("Mobile")
            email = st.text_input("Email")
        with c2:
            budget = st.number_input("Budget", min_value=0.0, step=1000.0)
            preferred_location = st.text_input("Preferred Location")
            property_type = st.selectbox("Property Type", PROPERTY_TYPES)
        with c3:
            source = st.selectbox("Source", LEAD_SOURCES)
            status = st.selectbox("Status", LEAD_STATUSES)
            assigned_agent = st.text_input("Assigned Agent")

        next_followup_date = st.date_input("Next Follow-up Date", value=datetime.date.today())
        requirement = st.text_area("Requirement")
        notes = st.text_area("Notes")

        submitted = st.form_submit_button("Save Lead", type="primary", use_container_width=True)

    if submitted:
        if is_blank(lead_name):
            st.error("Lead Name is required.")
        else:
            run_query(
                """INSERT INTO leads (tenant_id, lead_name, mobile, email, requirement, budget, preferred_location,
                    property_type, source, assigned_agent, status, next_followup_date, notes, date_added)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (tenant_id, lead_name, mobile, email, requirement, safe_float(budget), preferred_location,
                 property_type, source, assigned_agent, status, str(next_followup_date), notes, today_str()),
            )
            log_activity(tenant_id, "Lead Added", f"Added lead '{lead_name}'")
            st.success("Lead saved successfully.")
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


def _render_manage(tenant_id, currency_symbol, date_format):
    st.markdown('<div class="sn-card">', unsafe_allow_html=True)

    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        search = st.text_input("🔍 Search by name / mobile / email / location")
    with c2:
        f_status = st.selectbox("Status", ["All"] + LEAD_STATUSES)
    with c3:
        f_source = st.selectbox("Source", ["All"] + LEAD_SOURCES)

    sql = "SELECT * FROM leads WHERE tenant_id = ?"
    params = [tenant_id]
    if search:
        sql += " AND (lead_name LIKE ? OR mobile LIKE ? OR email LIKE ? OR preferred_location LIKE ?)"
        like = f"%{search}%"
        params += [like, like, like, like]
    if f_status != "All":
        sql += " AND status = ?"
        params.append(f_status)
    if f_source != "All":
        sql += " AND source = ?"
        params.append(f_source)
    sql += " ORDER BY id DESC"

    df = run_df(sql, tuple(params))

    if df.empty:
        st.info("No leads found.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    today = datetime.date.today().isoformat()

    def is_overdue(r):
        return bool(r["next_followup_date"]) and str(r["next_followup_date"]) < today and r["status"] not in ("Converted", "Lost")

    display_df = df.copy()
    display_df["overdue"] = display_df.apply(is_overdue, axis=1)
    display_df["Follow-up"] = display_df.apply(
        lambda r: f"⚠️ {fmt_date(r['next_followup_date'], date_format)}" if r["overdue"] else fmt_date(r["next_followup_date"], date_format),
        axis=1,
    )
    display_df["budget_display"] = display_df["budget"].apply(lambda v: fmt_currency(v, currency_symbol))
    display_df["date_added_display"] = display_df["date_added"].apply(lambda v: fmt_date(v, date_format))

    overdue_count = int(display_df["overdue"].sum())
    if overdue_count:
        st.markdown(f'<div class="sn-banner sn-banner-warn">⚠️ {overdue_count} lead(s) have overdue follow-ups.</div>', unsafe_allow_html=True)

    st.dataframe(
        display_df[["id", "lead_name", "mobile", "status", "source", "budget_display",
                    "Follow-up", "date_added_display"]].rename(columns={
            "lead_name": "Name", "mobile": "Mobile", "status": "Status", "source": "Source",
            "budget_display": "Budget", "date_added_display": "Added",
        }),
        use_container_width=True, hide_index=True,
    )

    ce1, ce2 = st.columns(2)
    with ce1:
        st.download_button(
            "⬇️ Export Excel", dataframe_to_excel_bytes(display_df[[
                "lead_name", "mobile", "email", "status", "source", "budget", "preferred_location",
                "next_followup_date"]], "Leads", "Leads Report"),
            file_name="leads.xlsx", use_container_width=True,
        )
    with ce2:
        st.download_button(
            "⬇️ Export PDF", dataframe_to_pdf_bytes(display_df[[
                "lead_name", "mobile", "email", "status", "source", "budget", "preferred_location",
                "next_followup_date"]], "Leads Report"),
            file_name="leads.pdf", use_container_width=True,
        )

    st.markdown("---")
    options = {f"{row.id} — {row.lead_name}": row.id for row in df.itertuples()}
    selected_label = st.selectbox("Select a lead to view / edit / delete", list(options.keys()))
    selected_id = options[selected_label]
    _render_detail(tenant_id, selected_id, currency_symbol, date_format)

    st.markdown('</div>', unsafe_allow_html=True)


def _render_detail(tenant_id, lead_id, currency_symbol, date_format):
    row = run_query("SELECT * FROM leads WHERE id = ? AND tenant_id = ?", (lead_id, tenant_id), fetchone=True)
    if not row:
        st.warning("Lead not found.")
        return

    st.markdown(f"#### {row['lead_name']}  {badge_html(row['status'])}", unsafe_allow_html=True)
    dc1, dc2, dc3 = st.columns(3)
    with dc1:
        st.write(f"**Mobile:** {row['mobile']} | **Email:** {row['email']}")
        st.write(f"**Preferred Location:** {row['preferred_location']}")
    with dc2:
        st.write(f"**Budget:** {fmt_currency(row['budget'], currency_symbol)}")
        st.write(f"**Property Type:** {row['property_type']}")
    with dc3:
        st.write(f"**Source:** {row['source']} | **Agent:** {row['assigned_agent']}")
        st.write(f"**Next Follow-up:** {fmt_date(row['next_followup_date'], date_format)}")

    if row.get("requirement"):
        st.write(f"**Requirement:** {row['requirement']}")
    if row.get("notes"):
        st.write(f"**Notes:** {row['notes']}")

    st.markdown("---")
    tab_edit, tab_convert, tab_delete = st.tabs(["✏️ Edit", "🔄 Convert to Customer", "🗑️ Delete"])

    with tab_edit:
        with st.form(f"edit_lead_{lead_id}"):
            e1, e2, e3 = st.columns(3)
            with e1:
                lead_name = st.text_input("Name", value=row["lead_name"])
                mobile = st.text_input("Mobile", value=row["mobile"] or "")
                email = st.text_input("Email", value=row["email"] or "")
            with e2:
                budget = st.number_input("Budget", min_value=0.0, step=1000.0, value=safe_float(row["budget"]))
                preferred_location = st.text_input("Preferred Location", value=row["preferred_location"] or "")
                property_type = st.selectbox("Property Type", PROPERTY_TYPES, index=_safe_index(PROPERTY_TYPES, row["property_type"]))
            with e3:
                source = st.selectbox("Source", LEAD_SOURCES, index=_safe_index(LEAD_SOURCES, row["source"]))
                status = st.selectbox("Status", LEAD_STATUSES, index=_safe_index(LEAD_STATUSES, row["status"]))
                assigned_agent = st.text_input("Assigned Agent", value=row["assigned_agent"] or "")
            try:
                current_followup = datetime.date.fromisoformat(str(row["next_followup_date"])[:10])
            except (ValueError, TypeError):
                current_followup = datetime.date.today()
            next_followup_date = st.date_input("Next Follow-up Date", value=current_followup)
            requirement = st.text_area("Requirement", value=row["requirement"] or "")
            notes = st.text_area("Notes", value=row["notes"] or "")

            update_submitted = st.form_submit_button("Update Lead", type="primary", use_container_width=True)

        if update_submitted:
            run_query(
                """UPDATE leads SET lead_name=?, mobile=?, email=?, budget=?, preferred_location=?, property_type=?,
                   source=?, status=?, assigned_agent=?, next_followup_date=?, requirement=?, notes=?
                   WHERE id = ? AND tenant_id = ?""",
                (lead_name, mobile, email, safe_float(budget), preferred_location, property_type, source, status,
                 assigned_agent, str(next_followup_date), requirement, notes, lead_id, tenant_id),
            )
            log_activity(tenant_id, "Lead Updated", f"Updated lead '{lead_name}'")
            st.success("Lead updated.")
            st.rerun()

    with tab_convert:
        if row["status"] == "Converted":
            st.info("This lead has already been converted to a customer.")
        else:
            st.write("Create a customer record from this lead's details.")
            if st.button("Convert to Customer", key=f"convert_lead_{lead_id}", type="primary"):
                run_query(
                    """INSERT INTO customers (tenant_id, name, mobile, email, requirement, preferred_location,
                        budget, property_type_required, source, assigned_agent, date_added)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (tenant_id, row["lead_name"], row["mobile"], row["email"], row["requirement"],
                     row["preferred_location"], row["budget"], row["property_type"], row["source"],
                     row["assigned_agent"], today_str()),
                )
                run_query("UPDATE leads SET status = 'Converted' WHERE id = ? AND tenant_id = ?", (lead_id, tenant_id))
                log_activity(tenant_id, "Lead Converted", f"Converted lead '{row['lead_name']}' to customer")
                st.success("Lead converted to customer.")
                st.rerun()

    with tab_delete:
        st.warning(f"This will permanently delete '{row['lead_name']}'.")
        confirm = st.checkbox("I confirm I want to delete this lead", key=f"confirm_del_lead_{lead_id}")
        if st.button("Delete Lead", key=f"del_lead_{lead_id}", disabled=not confirm):
            run_query("DELETE FROM leads WHERE id = ? AND tenant_id = ?", (lead_id, tenant_id))
            log_activity(tenant_id, "Lead Deleted", f"Deleted lead '{row['lead_name']}'")
            st.success("Lead deleted.")
            st.rerun()


def _safe_index(options, value):
    try:
        return options.index(value)
    except (ValueError, TypeError):
        return 0
