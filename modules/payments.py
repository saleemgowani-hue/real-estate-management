"""
modules/payments.py
Payment tracking against deals: recording a payment re-derives that deal's
payment_status the same way modules/deals.py does (booking_amount + sum of
all payments for the deal, compared to final_amount), so both modules
always agree. Optional Razorpay payment-link generation via
payment_gateway.py — manual entry is always the primary, always-working flow.
"""

import datetime
import streamlit as st

from config import PAYMENT_MODES
from database import run_query, run_df, log_activity
from utils import fmt_date, fmt_currency, safe_float, dataframe_to_excel_bytes, dataframe_to_pdf_bytes
import payment_gateway


def render(tenant_id, currency_symbol, date_format):
    st.markdown(
        '<div class="sn-section-title">💰 Payments</div>'
        '<div class="sn-section-sub">Record and track payments received against deals.</div>',
        unsafe_allow_html=True,
    )
    tab_add, tab_manage = st.tabs(["➕ Record Payment", "📋 Manage Payments"])
    with tab_add:
        _render_add_form(tenant_id, currency_symbol)
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


def _sync_deal_payment_status(tenant_id, deal_id):
    deal = run_query("SELECT final_amount, booking_amount FROM deals WHERE id = ? AND tenant_id = ?", (deal_id, tenant_id), fetchone=True)
    if not deal:
        return
    paid_so_far = _paid_so_far(deal_id, deal["booking_amount"])
    payment_status = _derive_payment_status(deal["final_amount"], paid_so_far)
    run_query("UPDATE deals SET payment_status = ? WHERE id = ? AND tenant_id = ?", (payment_status, deal_id, tenant_id))


def _render_add_form(tenant_id, currency_symbol):
    st.markdown('<div class="sn-card">', unsafe_allow_html=True)
    deals_df = run_df(
        """SELECT d.id, c.name AS customer_name, p.property_name, d.final_amount, d.booking_amount, d.customer_id, d.property_id,
                  c.email AS customer_email, c.mobile AS customer_mobile
           FROM deals d LEFT JOIN customers c ON d.customer_id = c.id LEFT JOIN properties p ON d.property_id = p.id
           WHERE d.tenant_id = ? ORDER BY d.id DESC""",
        (tenant_id,),
    )
    if deals_df.empty:
        st.info("No deals found yet. Add a deal first in the Deals / Sales module.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    deal_options = {}
    for r in deals_df.itertuples():
        paid_so_far = _paid_so_far(r.id, r.booking_amount)
        due = max(safe_float(r.final_amount) - paid_so_far, 0)
        deal_options[f"#{r.id} — {r.customer_name} — {r.property_name} (Due: {fmt_currency(due, currency_symbol)})"] = r.id

    selected_label = st.selectbox("Deal *", list(deal_options.keys()))
    selected_deal_id = deal_options[selected_label]
    selected_row = deals_df[deals_df["id"] == selected_deal_id].iloc[0]

    with st.form("add_payment_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            payment_date = st.date_input("Payment Date", value=datetime.date.today())
            amount = st.number_input("Amount *", min_value=0.0, step=1000.0)
        with c2:
            payment_mode = st.selectbox("Payment Mode", PAYMENT_MODES)
            transaction_number = st.text_input("Transaction Number")
        remarks = st.text_area("Remarks")

        submitted = st.form_submit_button("Save Payment", type="primary", use_container_width=True)

    if submitted:
        if amount <= 0:
            st.error("Amount must be greater than zero.")
        else:
            run_query(
                """INSERT INTO payments (tenant_id, deal_id, customer_id, property_id, payment_date, amount,
                    payment_mode, transaction_number, remarks) VALUES (?,?,?,?,?,?,?,?,?)""",
                (tenant_id, selected_deal_id, int(selected_row["customer_id"]) if selected_row["customer_id"] else None,
                 int(selected_row["property_id"]) if selected_row["property_id"] else None,
                 payment_date.isoformat(), safe_float(amount), payment_mode, transaction_number, remarks),
            )
            _sync_deal_payment_status(tenant_id, selected_deal_id)
            log_activity(tenant_id, "Payment Recorded", f"Payment of {fmt_currency(amount, currency_symbol)} recorded for Deal #{selected_deal_id}")
            st.success("Payment recorded successfully.")
            st.rerun()

    if payment_gateway.is_gateway_configured(tenant_id):
        st.markdown("---")
        st.caption("Optional: generate an online payment link for this deal via your configured payment gateway.")
        link_amount = st.number_input("Link Amount", min_value=0.0, step=1000.0, key="link_amount")
        if st.button("🔗 Generate Payment Link"):
            success, result = payment_gateway.create_payment_link(
                tenant_id, link_amount, f"Payment for Deal #{selected_deal_id}",
                customer_name=selected_row["customer_name"] or "",
                customer_email=selected_row.get("customer_email") or "",
                customer_contact=selected_row.get("customer_mobile") or "",
                reference_id=str(selected_deal_id),
            )
            if success:
                st.success("Payment link generated.")
                st.code(result.get("short_url", ""))
            else:
                st.error(result)
    st.markdown('</div>', unsafe_allow_html=True)


def _render_manage(tenant_id, currency_symbol, date_format):
    st.markdown('<div class="sn-card">', unsafe_allow_html=True)

    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        search = st.text_input("🔍 Search by customer / property / transaction #")
    with c2:
        f_mode = st.selectbox("Payment Mode", ["All"] + PAYMENT_MODES)
    with c3:
        date_from = st.date_input("From", value=None, key="pay_from")
    date_to = st.date_input("To", value=None, key="pay_to")

    sql = """SELECT pay.*, c.name AS customer_name, p.property_name
              FROM payments pay LEFT JOIN customers c ON pay.customer_id = c.id
              LEFT JOIN properties p ON pay.property_id = p.id WHERE pay.tenant_id = ?"""
    params = [tenant_id]
    if search:
        sql += " AND (c.name LIKE ? OR p.property_name LIKE ? OR pay.transaction_number LIKE ?)"
        like = f"%{search}%"
        params += [like, like, like]
    if f_mode != "All":
        sql += " AND pay.payment_mode = ?"
        params.append(f_mode)
    if date_from:
        sql += " AND pay.payment_date >= ?"
        params.append(date_from.isoformat())
    if date_to:
        sql += " AND pay.payment_date <= ?"
        params.append(date_to.isoformat())
    sql += " ORDER BY pay.id DESC"

    df = run_df(sql, tuple(params))
    if df.empty:
        st.info("No payments found.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    display_df = df.copy()
    display_df["amount_display"] = display_df["amount"].apply(lambda v: fmt_currency(v, currency_symbol))
    display_df["date_display"] = display_df["payment_date"].apply(lambda v: fmt_date(v, date_format))

    st.dataframe(
        display_df[["id", "customer_name", "property_name", "date_display", "amount_display", "payment_mode",
                    "transaction_number"]].rename(columns={
            "customer_name": "Customer", "property_name": "Property", "date_display": "Date",
            "amount_display": "Amount", "payment_mode": "Mode", "transaction_number": "Transaction #",
        }),
        use_container_width=True, hide_index=True,
    )

    total = df["amount"].apply(safe_float).sum()
    st.metric("Total (filtered)", fmt_currency(total, currency_symbol))

    ce1, ce2 = st.columns(2)
    export_cols = ["customer_name", "property_name", "payment_date", "amount", "payment_mode", "transaction_number", "remarks"]
    with ce1:
        st.download_button("⬇️ Export Excel", dataframe_to_excel_bytes(df[export_cols], "Payments", "Payments"),
                            file_name="payments.xlsx", use_container_width=True)
    with ce2:
        st.download_button("⬇️ Export PDF", dataframe_to_pdf_bytes(df[export_cols], "Payments"),
                            file_name="payments.pdf", use_container_width=True)

    st.markdown("---")
    options = {f"{row.id} — {row.customer_name} — {fmt_currency(row.amount, currency_symbol)}": row.id for row in df.itertuples()}
    selected_label = st.selectbox("Select a payment to edit / delete", list(options.keys()))
    selected_id = options[selected_label]
    _render_detail(tenant_id, selected_id, currency_symbol)

    st.markdown('</div>', unsafe_allow_html=True)


def _render_detail(tenant_id, payment_id, currency_symbol):
    row = run_query("SELECT * FROM payments WHERE id = ? AND tenant_id = ?", (payment_id, tenant_id), fetchone=True)
    if not row:
        st.warning("Payment not found.")
        return

    tab_edit, tab_delete = st.tabs(["✏️ Edit", "🗑️ Delete"])

    with tab_edit:
        with st.form(f"edit_payment_{payment_id}"):
            e1, e2 = st.columns(2)
            with e1:
                amount = st.number_input("Amount", min_value=0.0, step=1000.0, value=safe_float(row["amount"]))
                payment_mode = st.selectbox("Payment Mode", PAYMENT_MODES, index=_safe_index(PAYMENT_MODES, row["payment_mode"]))
            with e2:
                transaction_number = st.text_input("Transaction Number", value=row["transaction_number"] or "")
                remarks = st.text_area("Remarks", value=row["remarks"] or "")
            update_submitted = st.form_submit_button("Update Payment", type="primary", use_container_width=True)

        if update_submitted:
            run_query(
                "UPDATE payments SET amount=?, payment_mode=?, transaction_number=?, remarks=? WHERE id = ? AND tenant_id = ?",
                (safe_float(amount), payment_mode, transaction_number, remarks, payment_id, tenant_id),
            )
            if row["deal_id"]:
                _sync_deal_payment_status(tenant_id, row["deal_id"])
            log_activity(tenant_id, "Payment Updated", f"Payment #{payment_id} updated")
            st.success("Payment updated.")
            st.rerun()

    with tab_delete:
        st.warning("This will permanently delete this payment record and re-sync the linked deal's payment status.")
        confirm = st.checkbox("I confirm I want to delete this payment", key=f"confirm_del_pay_{payment_id}")
        if st.button("Delete Payment", key=f"del_pay_{payment_id}", disabled=not confirm):
            deal_id = row["deal_id"]
            run_query("DELETE FROM payments WHERE id = ? AND tenant_id = ?", (payment_id, tenant_id))
            if deal_id:
                _sync_deal_payment_status(tenant_id, deal_id)
            log_activity(tenant_id, "Payment Deleted", f"Payment #{payment_id} deleted")
            st.success("Payment deleted.")
            st.rerun()


def _safe_index(options, value):
    try:
        return options.index(value)
    except (ValueError, TypeError):
        return 0
