"""
modules/deals.py
Deals / Sales: add/search/edit/delete deals, payment-status derivation
(kept consistent with modules/payments.py), the Completed -> property
Sold/Rented side effect, Excel/PDF export.
"""

import datetime
import streamlit as st

from config import DEAL_STATUSES, PAYMENT_STATUSES
from database import run_query, run_df, log_activity
from utils import fmt_date, fmt_currency, safe_float, dataframe_to_excel_bytes, dataframe_to_pdf_bytes
from style import badge_html


def render(tenant_id, currency_symbol, date_format):
    st.markdown(
        '<div class="sn-section-title">🤝 Deals / Sales</div>'
        '<div class="sn-section-sub">Track deals from negotiation through to completion.</div>',
        unsafe_allow_html=True,
    )
    tab_add, tab_manage = st.tabs(["➕ Add Deal", "📋 Manage Deals"])
    with tab_add:
        _render_add_form(tenant_id)
    with tab_manage:
        _render_manage(tenant_id, currency_symbol, date_format)


def _paid_so_far(deal_id, booking_amount):
    row = run_query("SELECT COALESCE(SUM(amount),0) AS s FROM payments WHERE deal_id = ?", (deal_id,), fetchone=True)
    return safe_float(booking_amount) + safe_float(row["s"] if row else 0)


def _derive_payment_status(final_amount, paid_so_far):
    final_amount = safe_float(final_amount)
    if final_amount > 0 and paid_so_far >= final_amount:
        return "Paid"
    if paid_so_far > 0:
        return "Partial"
    return "Pending"


def _apply_completed_property_status(tenant_id, property_id, deal_status):
    if deal_status != "Completed" or not property_id:
        return
    prop = run_query("SELECT listing_type FROM properties WHERE id = ? AND tenant_id = ?", (property_id, tenant_id), fetchone=True)
    if not prop:
        return
    new_status = "Sold" if prop["listing_type"] == "Sale" else "Rented"
    run_query("UPDATE properties SET status = ? WHERE id = ? AND tenant_id = ?", (new_status, property_id, tenant_id))


def _render_add_form(tenant_id):
    st.markdown('<div class="sn-card">', unsafe_allow_html=True)
    customers_df = run_df("SELECT id, name FROM customers WHERE tenant_id = ? ORDER BY name", (tenant_id,))
    properties_df = run_df("SELECT id, property_name, status, listing_type FROM properties WHERE tenant_id = ? ORDER BY property_name", (tenant_id,))
    staff_rows = run_query("SELECT name FROM staff WHERE tenant_id = ? AND status = 'Active'", (tenant_id,), fetch=True)
    agent_names = [r["name"] for r in staff_rows] if staff_rows else []

    if customers_df.empty or properties_df.empty:
        st.info("Add at least one customer and one property before creating a deal.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    customer_options = {f"{r.id} — {r.name}": r.id for r in customers_df.itertuples()}
    property_options = {f"{r.id} — {r.property_name} ({r.status})": r.id for r in properties_df.itertuples()}

    with st.form("add_deal_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            customer_label = st.selectbox("Customer *", list(customer_options.keys()))
            property_label = st.selectbox("Property *", list(property_options.keys()))
            if agent_names:
                agent = st.selectbox("Agent", agent_names)
            else:
                agent = st.text_input("Agent")
            deal_date = st.date_input("Deal Date", value=datetime.date.today())
        with c2:
            deal_status = st.selectbox("Deal Status", DEAL_STATUSES)
            property_value = st.number_input("Property Value", min_value=0.0, step=1000.0)
            discount = st.number_input("Discount", min_value=0.0, step=1000.0)
            booking_amount = st.number_input("Booking Amount", min_value=0.0, step=1000.0)
            commission = st.number_input("Commission", min_value=0.0, step=100.0, help="Leave as 0 to auto-calculate 1% of the final amount.")
        remarks = st.text_area("Remarks")

        submitted = st.form_submit_button("Save Deal", type="primary", use_container_width=True)

    if submitted:
        customer_id = customer_options[customer_label]
        property_id = property_options[property_label]
        final_amount = safe_float(property_value) - safe_float(discount)
        commission_val = safe_float(commission) or round(final_amount * 0.01, 2)
        payment_status = _derive_payment_status(final_amount, safe_float(booking_amount))

        deal_id = run_query(
            """INSERT INTO deals (tenant_id, customer_id, property_id, agent, deal_date, property_value, discount,
                final_amount, booking_amount, commission, payment_status, deal_status, remarks)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (tenant_id, customer_id, property_id, agent, deal_date.isoformat(), safe_float(property_value),
             safe_float(discount), final_amount, safe_float(booking_amount), commission_val, payment_status,
             deal_status, remarks),
        )
        _apply_completed_property_status(tenant_id, property_id, deal_status)
        log_activity(tenant_id, "Deal Added", f"Deal #{deal_id} created")
        st.success("Deal saved successfully.")
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


def _render_manage(tenant_id, currency_symbol, date_format):
    st.markdown('<div class="sn-card">', unsafe_allow_html=True)

    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        search = st.text_input("🔍 Search by customer / property / agent")
    with c2:
        f_deal_status = st.selectbox("Deal Status", ["All"] + DEAL_STATUSES)
    with c3:
        f_payment_status = st.selectbox("Payment Status", ["All"] + PAYMENT_STATUSES)

    sql = """SELECT d.*, c.name AS customer_name, p.property_name AS property_name
              FROM deals d LEFT JOIN customers c ON d.customer_id = c.id
              LEFT JOIN properties p ON d.property_id = p.id WHERE d.tenant_id = ?"""
    params = [tenant_id]
    if search:
        sql += " AND (c.name LIKE ? OR p.property_name LIKE ? OR d.agent LIKE ?)"
        like = f"%{search}%"
        params += [like, like, like]
    if f_deal_status != "All":
        sql += " AND d.deal_status = ?"
        params.append(f_deal_status)
    if f_payment_status != "All":
        sql += " AND d.payment_status = ?"
        params.append(f_payment_status)
    sql += " ORDER BY d.id DESC"

    df = run_df(sql, tuple(params))
    if df.empty:
        st.info("No deals found.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    display_df = df.copy()
    display_df["final_display"] = display_df["final_amount"].apply(lambda v: fmt_currency(v, currency_symbol))
    display_df["booking_display"] = display_df["booking_amount"].apply(lambda v: fmt_currency(v, currency_symbol))
    display_df["date_display"] = display_df["deal_date"].apply(lambda v: fmt_date(v, date_format))

    st.dataframe(
        display_df[["id", "customer_name", "property_name", "agent", "date_display", "final_display",
                    "booking_display", "deal_status", "payment_status"]].rename(columns={
            "customer_name": "Customer", "property_name": "Property", "agent": "Agent",
            "date_display": "Deal Date", "final_display": "Final Amount", "booking_display": "Booking",
            "deal_status": "Deal Status", "payment_status": "Payment Status",
        }),
        use_container_width=True, hide_index=True,
    )

    ce1, ce2 = st.columns(2)
    export_cols = ["customer_name", "property_name", "agent", "deal_date", "property_value", "discount",
                    "final_amount", "booking_amount", "commission", "payment_status", "deal_status"]
    with ce1:
        st.download_button("⬇️ Export Excel", dataframe_to_excel_bytes(df[export_cols], "Deals", "Deals / Sales"),
                            file_name="deals.xlsx", use_container_width=True)
    with ce2:
        st.download_button("⬇️ Export PDF", dataframe_to_pdf_bytes(df[export_cols], "Deals / Sales"),
                            file_name="deals.pdf", use_container_width=True)

    st.markdown("---")
    options = {f"{row.id} — {row.customer_name} — {row.property_name}": row.id for row in df.itertuples()}
    selected_label = st.selectbox("Select a deal to view / edit / delete", list(options.keys()))
    selected_id = options[selected_label]
    _render_detail(tenant_id, selected_id, currency_symbol, date_format)

    st.markdown('</div>', unsafe_allow_html=True)


def _render_detail(tenant_id, deal_id, currency_symbol, date_format):
    row = run_query("SELECT * FROM deals WHERE id = ? AND tenant_id = ?", (deal_id, tenant_id), fetchone=True)
    if not row:
        st.warning("Deal not found.")
        return

    customer = run_query("SELECT name FROM customers WHERE id = ?", (row["customer_id"],), fetchone=True) or {}
    property_row = run_query("SELECT property_name, status, listing_type FROM properties WHERE id = ?", (row["property_id"],), fetchone=True) or {}

    st.markdown(
        f"#### Deal #{row['id']} — {customer.get('name', '-')}  {badge_html(row['deal_status'])} {badge_html(row['payment_status'])}",
        unsafe_allow_html=True,
    )

    dc1, dc2, dc3 = st.columns(3)
    with dc1:
        st.write(f"**Customer:** {customer.get('name', '-')}")
        st.write(f"**Property:** {property_row.get('property_name', '-')} ({property_row.get('status', '-')})")
        st.write(f"**Agent:** {row['agent']}")
    with dc2:
        st.write(f"**Deal Date:** {fmt_date(row['deal_date'], date_format)}")
        st.write(f"**Property Value:** {fmt_currency(row['property_value'], currency_symbol)}")
        st.write(f"**Discount:** {fmt_currency(row['discount'], currency_symbol)}")
    with dc3:
        st.write(f"**Final Amount:** {fmt_currency(row['final_amount'], currency_symbol)}")
        st.write(f"**Booking Amount:** {fmt_currency(row['booking_amount'], currency_symbol)}")
        st.write(f"**Commission:** {fmt_currency(row['commission'], currency_symbol)}")

    if row.get("remarks"):
        st.write(f"**Remarks:** {row['remarks']}")

    st.markdown("---")
    tab_edit, tab_delete = st.tabs(["✏️ Edit", "🗑️ Delete"])

    with tab_edit:
        with st.form(f"edit_deal_{deal_id}"):
            e1, e2 = st.columns(2)
            with e1:
                property_value = st.number_input("Property Value", min_value=0.0, step=1000.0, value=safe_float(row["property_value"]))
                discount = st.number_input("Discount", min_value=0.0, step=1000.0, value=safe_float(row["discount"]))
                booking_amount = st.number_input("Booking Amount", min_value=0.0, step=1000.0, value=safe_float(row["booking_amount"]))
                commission = st.number_input("Commission", min_value=0.0, step=100.0, value=safe_float(row["commission"]))
            with e2:
                deal_status = st.selectbox("Deal Status", DEAL_STATUSES, index=_safe_index(DEAL_STATUSES, row["deal_status"]))
                agent = st.text_input("Agent", value=row["agent"] or "")
                remarks = st.text_area("Remarks", value=row["remarks"] or "")

            update_submitted = st.form_submit_button("Update Deal", type="primary", use_container_width=True)

        if update_submitted:
            final_amount = safe_float(property_value) - safe_float(discount)
            paid_so_far = _paid_so_far(deal_id, booking_amount)
            payment_status = _derive_payment_status(final_amount, paid_so_far)
            run_query(
                """UPDATE deals SET property_value=?, discount=?, final_amount=?, booking_amount=?, commission=?,
                   payment_status=?, deal_status=?, agent=?, remarks=? WHERE id = ? AND tenant_id = ?""",
                (safe_float(property_value), safe_float(discount), final_amount, safe_float(booking_amount),
                 safe_float(commission), payment_status, deal_status, agent, remarks, deal_id, tenant_id),
            )
            _apply_completed_property_status(tenant_id, row["property_id"], deal_status)
            log_activity(tenant_id, "Deal Updated", f"Deal #{deal_id} updated")
            st.success("Deal updated.")
            st.rerun()

    with tab_delete:
        st.warning("This will permanently delete this deal record.")
        confirm = st.checkbox("I confirm I want to delete this deal", key=f"confirm_del_deal_{deal_id}")
        if st.button("Delete Deal", key=f"del_deal_{deal_id}", disabled=not confirm):
            run_query("DELETE FROM deals WHERE id = ? AND tenant_id = ?", (deal_id, tenant_id))
            log_activity(tenant_id, "Deal Deleted", f"Deal #{deal_id} deleted")
            st.success("Deal deleted.")
            st.rerun()


def _safe_index(options, value):
    try:
        return options.index(value)
    except (ValueError, TypeError):
        return 0
