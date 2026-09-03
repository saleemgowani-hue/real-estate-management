"""
modules/expenses.py
Business expense tracking: add/search/edit/delete, category breakdown,
Excel/PDF export.
"""

import datetime
import streamlit as st

from config import EXPENSE_CATEGORIES, PAYMENT_MODES
from database import run_query, run_df, log_activity
from utils import fmt_date, fmt_currency, safe_float, dataframe_to_excel_bytes, dataframe_to_pdf_bytes


def render(tenant_id, currency_symbol, date_format):
    st.markdown(
        '<div class="sn-section-title">💸 Expenses</div>'
        '<div class="sn-section-sub">Track day-to-day business expenses.</div>',
        unsafe_allow_html=True,
    )
    tab_add, tab_manage = st.tabs(["➕ Add Expense", "📋 Manage Expenses"])
    with tab_add:
        _render_add_form(tenant_id)
    with tab_manage:
        _render_manage(tenant_id, currency_symbol, date_format)


def _agent_options(tenant_id):
    rows = run_query("SELECT name FROM staff WHERE tenant_id = ? AND status = 'Active'", (tenant_id,), fetch=True)
    return [r["name"] for r in rows] if rows else []


def _render_add_form(tenant_id):
    st.markdown('<div class="sn-card">', unsafe_allow_html=True)
    agent_names = _agent_options(tenant_id)

    with st.form("add_expense_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            expense_date = st.date_input("Expense Date", value=datetime.date.today())
            category = st.selectbox("Category", EXPENSE_CATEGORIES)
            amount = st.number_input("Amount *", min_value=0.0, step=100.0)
        with c2:
            payment_mode = st.selectbox("Payment Mode", PAYMENT_MODES)
            if agent_names:
                paid_by = st.selectbox("Paid By", agent_names)
            else:
                paid_by = st.text_input("Paid By")
        description = st.text_input("Description")
        remarks = st.text_area("Remarks")

        submitted = st.form_submit_button("Save Expense", type="primary", use_container_width=True)

    if submitted:
        if amount <= 0:
            st.error("Amount must be greater than zero.")
        else:
            expense_id = run_query(
                """INSERT INTO expenses (tenant_id, expense_date, category, description, amount, payment_mode, paid_by, remarks)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (tenant_id, expense_date.isoformat(), category, description, safe_float(amount), payment_mode, paid_by, remarks),
            )
            log_activity(tenant_id, "Expense Added", f"Expense #{expense_id} ({category}) added")
            st.success("Expense saved successfully.")
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


def _render_manage(tenant_id, currency_symbol, date_format):
    st.markdown('<div class="sn-card">', unsafe_allow_html=True)

    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        search = st.text_input("🔍 Search by description / paid by")
    with c2:
        f_category = st.selectbox("Category", ["All"] + EXPENSE_CATEGORIES)
    with c3:
        date_from = st.date_input("From", value=None, key="exp_from")
    date_to = st.date_input("To", value=None, key="exp_to")

    sql = "SELECT * FROM expenses WHERE tenant_id = ?"
    params = [tenant_id]
    if search:
        sql += " AND (description LIKE ? OR paid_by LIKE ?)"
        like = f"%{search}%"
        params += [like, like]
    if f_category != "All":
        sql += " AND category = ?"
        params.append(f_category)
    if date_from:
        sql += " AND expense_date >= ?"
        params.append(date_from.isoformat())
    if date_to:
        sql += " AND expense_date <= ?"
        params.append(date_to.isoformat())
    sql += " ORDER BY id DESC"

    df = run_df(sql, tuple(params))
    if df.empty:
        st.info("No expenses found.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    display_df = df.copy()
    display_df["amount_display"] = display_df["amount"].apply(lambda v: fmt_currency(v, currency_symbol))
    display_df["date_display"] = display_df["expense_date"].apply(lambda v: fmt_date(v, date_format))

    st.dataframe(
        display_df[["id", "date_display", "category", "description", "amount_display", "payment_mode", "paid_by"]].rename(columns={
            "date_display": "Date", "category": "Category", "description": "Description",
            "amount_display": "Amount", "payment_mode": "Mode", "paid_by": "Paid By",
        }),
        use_container_width=True, hide_index=True,
    )

    total = df["amount"].apply(safe_float).sum()
    st.metric("Total (filtered)", fmt_currency(total, currency_symbol))

    by_category = df.groupby("category")["amount"].sum().sort_values(ascending=False)
    if not by_category.empty:
        st.bar_chart(by_category)

    ce1, ce2 = st.columns(2)
    export_cols = ["expense_date", "category", "description", "amount", "payment_mode", "paid_by", "remarks"]
    with ce1:
        st.download_button("⬇️ Export Excel", dataframe_to_excel_bytes(df[export_cols], "Expenses", "Expenses"),
                            file_name="expenses.xlsx", use_container_width=True)
    with ce2:
        st.download_button("⬇️ Export PDF", dataframe_to_pdf_bytes(df[export_cols], "Expenses"),
                            file_name="expenses.pdf", use_container_width=True)

    st.markdown("---")
    options = {f"{row.id} — {row.category} — {fmt_currency(row.amount, currency_symbol)} ({row.expense_date})": row.id for row in df.itertuples()}
    selected_label = st.selectbox("Select an expense to edit / delete", list(options.keys()))
    selected_id = options[selected_label]
    _render_detail(tenant_id, selected_id)

    st.markdown('</div>', unsafe_allow_html=True)


def _render_detail(tenant_id, expense_id):
    row = run_query("SELECT * FROM expenses WHERE id = ? AND tenant_id = ?", (expense_id, tenant_id), fetchone=True)
    if not row:
        st.warning("Expense not found.")
        return

    agent_names = _agent_options(tenant_id)
    tab_edit, tab_delete = st.tabs(["✏️ Edit", "🗑️ Delete"])

    with tab_edit:
        with st.form(f"edit_expense_{expense_id}"):
            e1, e2 = st.columns(2)
            with e1:
                category = st.selectbox("Category", EXPENSE_CATEGORIES, index=_safe_index(EXPENSE_CATEGORIES, row["category"]))
                amount = st.number_input("Amount", min_value=0.0, step=100.0, value=safe_float(row["amount"]))
                payment_mode = st.selectbox("Payment Mode", PAYMENT_MODES, index=_safe_index(PAYMENT_MODES, row["payment_mode"]))
            with e2:
                if agent_names:
                    paid_by = st.selectbox("Paid By", agent_names, index=_safe_index(agent_names, row["paid_by"]))
                else:
                    paid_by = st.text_input("Paid By", value=row["paid_by"] or "")
                description = st.text_input("Description", value=row["description"] or "")
                remarks = st.text_area("Remarks", value=row["remarks"] or "")
            update_submitted = st.form_submit_button("Update Expense", type="primary", use_container_width=True)

        if update_submitted:
            run_query(
                "UPDATE expenses SET category=?, description=?, amount=?, payment_mode=?, paid_by=?, remarks=? WHERE id = ? AND tenant_id = ?",
                (category, description, safe_float(amount), payment_mode, paid_by, remarks, expense_id, tenant_id),
            )
            log_activity(tenant_id, "Expense Updated", f"Expense #{expense_id} updated")
            st.success("Expense updated.")
            st.rerun()

    with tab_delete:
        st.warning("This will permanently delete this expense record.")
        confirm = st.checkbox("I confirm I want to delete this expense", key=f"confirm_del_exp_{expense_id}")
        if st.button("Delete Expense", key=f"del_exp_{expense_id}", disabled=not confirm):
            run_query("DELETE FROM expenses WHERE id = ? AND tenant_id = ?", (expense_id, tenant_id))
            log_activity(tenant_id, "Expense Deleted", f"Expense #{expense_id} deleted")
            st.success("Expense deleted.")
            st.rerun()


def _safe_index(options, value):
    try:
        return options.index(value)
    except (ValueError, TypeError):
        return 0
