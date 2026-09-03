"""
modules/customers.py
Customer database: add/search/edit/delete customers, Excel/PDF export.
"""

import streamlit as st

from config import PROPERTY_TYPES, LEAD_SOURCES
from database import run_query, run_df, log_activity
from utils import today_str, fmt_date, fmt_currency, safe_float, is_blank, dataframe_to_excel_bytes, dataframe_to_pdf_bytes

BUY_OR_RENT_OPTIONS = ["Buying", "Renting"]


def render(tenant_id, currency_symbol, date_format):
    st.markdown(
        '<div class="sn-section-title">👥 Customers</div>'
        '<div class="sn-section-sub">Add, search, and manage your customer database.</div>',
        unsafe_allow_html=True,
    )

    tab_add, tab_manage = st.tabs(["➕ Add Customer", "📋 Manage Customers"])

    with tab_add:
        _render_add_form(tenant_id)

    with tab_manage:
        _render_manage(tenant_id, currency_symbol, date_format)


def _render_add_form(tenant_id):
    st.markdown('<div class="sn-card">', unsafe_allow_html=True)
    with st.form("add_customer_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            name = st.text_input("Customer Name *")
            mobile = st.text_input("Mobile")
            whatsapp = st.text_input("WhatsApp")
            email = st.text_input("Email")
        with c2:
            preferred_location = st.text_input("Preferred Location")
            budget = st.number_input("Budget", min_value=0.0, step=1000.0)
            property_type_required = st.selectbox("Property Type Required", PROPERTY_TYPES)
            buy_or_rent = st.selectbox("Buying / Renting", BUY_OR_RENT_OPTIONS)
        with c3:
            source = st.selectbox("Source", LEAD_SOURCES)
            assigned_agent = st.text_input("Assigned Agent")
            address = st.text_area("Address", height=68)

        requirement = st.text_area("Requirement")
        notes = st.text_area("Notes")

        submitted = st.form_submit_button("Save Customer", type="primary", use_container_width=True)

    if submitted:
        if is_blank(name):
            st.error("Customer Name is required.")
        else:
            run_query(
                """INSERT INTO customers (tenant_id, name, mobile, whatsapp, email, address, requirement,
                    preferred_location, budget, property_type_required, buy_or_rent, source, assigned_agent,
                    notes, date_added) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (tenant_id, name, mobile, whatsapp, email, address, requirement, preferred_location,
                 safe_float(budget), property_type_required, buy_or_rent, source, assigned_agent, notes, today_str()),
            )
            log_activity(tenant_id, "Customer Added", f"Added customer '{name}'")
            st.success("Customer saved successfully.")
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


def _render_manage(tenant_id, currency_symbol, date_format):
    st.markdown('<div class="sn-card">', unsafe_allow_html=True)

    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        search = st.text_input("🔍 Search by name / mobile / email / location")
    with c2:
        f_type = st.selectbox("Property Type", ["All"] + PROPERTY_TYPES)
    with c3:
        f_buy_rent = st.selectbox("Buying / Renting", ["All"] + BUY_OR_RENT_OPTIONS)

    sql = "SELECT * FROM customers WHERE tenant_id = ?"
    params = [tenant_id]
    if search:
        sql += " AND (name LIKE ? OR mobile LIKE ? OR email LIKE ? OR preferred_location LIKE ?)"
        like = f"%{search}%"
        params += [like, like, like, like]
    if f_type != "All":
        sql += " AND property_type_required = ?"
        params.append(f_type)
    if f_buy_rent != "All":
        sql += " AND buy_or_rent = ?"
        params.append(f_buy_rent)
    sql += " ORDER BY id DESC"

    df = run_df(sql, tuple(params))

    if df.empty:
        st.info("No customers found.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    display_df = df.copy()
    display_df["budget_display"] = display_df["budget"].apply(lambda v: fmt_currency(v, currency_symbol))
    display_df["date_added_display"] = display_df["date_added"].apply(lambda v: fmt_date(v, date_format))

    st.dataframe(
        display_df[["id", "name", "mobile", "preferred_location", "budget_display",
                    "property_type_required", "buy_or_rent", "source", "date_added_display"]].rename(columns={
            "name": "Name", "mobile": "Mobile", "preferred_location": "Preferred Location",
            "budget_display": "Budget", "property_type_required": "Property Type", "buy_or_rent": "Buy/Rent",
            "source": "Source", "date_added_display": "Added",
        }),
        use_container_width=True, hide_index=True,
    )

    ce1, ce2 = st.columns(2)
    with ce1:
        st.download_button(
            "⬇️ Export Excel", dataframe_to_excel_bytes(display_df[[
                "name", "mobile", "email", "preferred_location", "budget", "property_type_required",
                "buy_or_rent", "source"]], "Customers", "Customer List"),
            file_name="customers.xlsx", use_container_width=True,
        )
    with ce2:
        st.download_button(
            "⬇️ Export PDF", dataframe_to_pdf_bytes(display_df[[
                "name", "mobile", "email", "preferred_location", "budget", "property_type_required",
                "buy_or_rent", "source"]], "Customer List"),
            file_name="customers.pdf", use_container_width=True,
        )

    st.markdown("---")
    options = {f"{row.id} — {row.name}": row.id for row in df.itertuples()}
    selected_label = st.selectbox("Select a customer to view / edit / delete", list(options.keys()))
    selected_id = options[selected_label]
    _render_detail(tenant_id, selected_id, currency_symbol, date_format)

    st.markdown('</div>', unsafe_allow_html=True)


def _render_detail(tenant_id, customer_id, currency_symbol, date_format):
    row = run_query("SELECT * FROM customers WHERE id = ? AND tenant_id = ?", (customer_id, tenant_id), fetchone=True)
    if not row:
        st.warning("Customer not found.")
        return

    st.markdown(f"#### {row['name']}", unsafe_allow_html=True)
    dc1, dc2, dc3 = st.columns(3)
    with dc1:
        st.write(f"**Mobile:** {row['mobile']} | **WhatsApp:** {row['whatsapp']}")
        st.write(f"**Email:** {row['email']}")
        st.write(f"**Address:** {row['address']}")
    with dc2:
        st.write(f"**Preferred Location:** {row['preferred_location']}")
        st.write(f"**Budget:** {fmt_currency(row['budget'], currency_symbol)}")
        st.write(f"**Requirement:** {row['requirement']}")
    with dc3:
        st.write(f"**Type:** {row['property_type_required']} ({row['buy_or_rent']})")
        st.write(f"**Source:** {row['source']} | **Agent:** {row['assigned_agent']}")
        st.write(f"**Added:** {fmt_date(row['date_added'], date_format)}")

    if row.get("notes"):
        st.write(f"**Notes:** {row['notes']}")

    st.markdown("---")
    tab_edit, tab_delete = st.tabs(["✏️ Edit", "🗑️ Delete"])

    with tab_edit:
        with st.form(f"edit_customer_{customer_id}"):
            e1, e2, e3 = st.columns(3)
            with e1:
                name = st.text_input("Name", value=row["name"])
                mobile = st.text_input("Mobile", value=row["mobile"] or "")
                email = st.text_input("Email", value=row["email"] or "")
            with e2:
                preferred_location = st.text_input("Preferred Location", value=row["preferred_location"] or "")
                budget = st.number_input("Budget", min_value=0.0, step=1000.0, value=safe_float(row["budget"]))
                property_type_required = st.selectbox("Property Type", PROPERTY_TYPES, index=_safe_index(PROPERTY_TYPES, row["property_type_required"]))
            with e3:
                buy_or_rent = st.selectbox("Buy/Rent", BUY_OR_RENT_OPTIONS, index=_safe_index(BUY_OR_RENT_OPTIONS, row["buy_or_rent"]))
                source = st.selectbox("Source", LEAD_SOURCES, index=_safe_index(LEAD_SOURCES, row["source"]))
                assigned_agent = st.text_input("Assigned Agent", value=row["assigned_agent"] or "")
            requirement = st.text_area("Requirement", value=row["requirement"] or "")
            notes = st.text_area("Notes", value=row["notes"] or "")

            update_submitted = st.form_submit_button("Update Customer", type="primary", use_container_width=True)

        if update_submitted:
            run_query(
                """UPDATE customers SET name=?, mobile=?, email=?, preferred_location=?, budget=?,
                   property_type_required=?, buy_or_rent=?, source=?, assigned_agent=?, requirement=?, notes=?
                   WHERE id = ? AND tenant_id = ?""",
                (name, mobile, email, preferred_location, safe_float(budget), property_type_required, buy_or_rent,
                 source, assigned_agent, requirement, notes, customer_id, tenant_id),
            )
            log_activity(tenant_id, "Customer Updated", f"Updated customer '{name}'")
            st.success("Customer updated.")
            st.rerun()

    with tab_delete:
        st.warning(f"This will permanently delete '{row['name']}'.")
        confirm = st.checkbox("I confirm I want to delete this customer", key=f"confirm_del_cust_{customer_id}")
        if st.button("Delete Customer", key=f"del_cust_{customer_id}", disabled=not confirm):
            run_query("DELETE FROM customers WHERE id = ? AND tenant_id = ?", (customer_id, tenant_id))
            log_activity(tenant_id, "Customer Deleted", f"Deleted customer '{row['name']}'")
            st.success("Customer deleted.")
            st.rerun()


def _safe_index(options, value):
    try:
        return options.index(value)
    except (ValueError, TypeError):
        return 0
