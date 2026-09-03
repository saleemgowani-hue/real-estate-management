"""
modules/staff.py
Agent / Staff management: staff records, optional login access creation
and revocation via auth.create_staff_login / auth.revoke_staff_login.
"""

import datetime
import streamlit as st

from config import STAFF_ROLES, STAFF_STATUSES, MIN_PASSWORD_LENGTH
from database import run_query, run_df, log_activity
from utils import fmt_date, fmt_currency, safe_float, dataframe_to_excel_bytes, dataframe_to_pdf_bytes
import auth


def render(tenant_id, currency_symbol, date_format, actor_id):
    st.markdown(
        '<div class="sn-section-title">👨‍💼 Agents / Staff</div>'
        '<div class="sn-section-sub">Manage staff records and their login access.</div>',
        unsafe_allow_html=True,
    )
    is_demo = auth.is_demo_tenant(tenant_id)
    tab_add, tab_manage, tab_logins = st.tabs(["➕ Add Staff", "📋 Manage Staff", "🔑 Login Access"])
    with tab_add:
        _render_add_form(tenant_id, is_demo)
    with tab_manage:
        _render_manage(tenant_id, currency_symbol, date_format, actor_id, is_demo)
    with tab_logins:
        _render_logins(tenant_id, actor_id, is_demo)


def _render_add_form(tenant_id, is_demo):
    st.markdown('<div class="sn-card">', unsafe_allow_html=True)
    if is_demo:
        st.info("This is the demo account — staff records can be viewed but not modified.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    with st.form("add_staff_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("Full Name *")
            mobile = st.text_input("Mobile")
            email = st.text_input("Email")
        with c2:
            role = st.selectbox("Role", STAFF_ROLES)
            joining_date = st.date_input("Joining Date", value=datetime.date.today())
            status = st.selectbox("Status", STAFF_STATUSES)
        s1, s2 = st.columns(2)
        with s1:
            salary = st.number_input("Salary", min_value=0.0, step=1000.0)
        with s2:
            commission_percent = st.number_input("Commission %", min_value=0.0, step=0.5)

        submitted = st.form_submit_button("Save Staff", type="primary", use_container_width=True)

    if submitted:
        if not name.strip():
            st.error("Full Name is required.")
        else:
            staff_id = run_query(
                """INSERT INTO staff (tenant_id, name, mobile, email, role, joining_date, salary, commission_percent, status)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (tenant_id, name.strip(), mobile, email, role, joining_date.isoformat(),
                 safe_float(salary), safe_float(commission_percent), status),
            )
            log_activity(tenant_id, "Staff Added", f"Staff #{staff_id} ({name}) added")
            st.success("Staff record saved successfully.")
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


def _render_manage(tenant_id, currency_symbol, date_format, actor_id, is_demo):
    st.markdown('<div class="sn-card">', unsafe_allow_html=True)

    c1, c2 = st.columns([2, 1])
    with c1:
        search = st.text_input("🔍 Search by name / mobile / email")
    with c2:
        f_role = st.selectbox("Role", ["All"] + STAFF_ROLES)

    sql = "SELECT * FROM staff WHERE tenant_id = ?"
    params = [tenant_id]
    if search:
        sql += " AND (name LIKE ? OR mobile LIKE ? OR email LIKE ?)"
        like = f"%{search}%"
        params += [like, like, like]
    if f_role != "All":
        sql += " AND role = ?"
        params.append(f_role)
    sql += " ORDER BY id DESC"

    df = run_df(sql, tuple(params))
    if df.empty:
        st.info("No staff records found.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    display_df = df.copy()
    display_df["salary_display"] = display_df["salary"].apply(lambda v: fmt_currency(v, currency_symbol))
    display_df["joining_display"] = display_df["joining_date"].apply(lambda v: fmt_date(v, date_format))

    st.dataframe(
        display_df[["id", "name", "role", "mobile", "email", "joining_display", "salary_display", "status"]].rename(columns={
            "name": "Name", "role": "Role", "mobile": "Mobile", "email": "Email",
            "joining_display": "Joining Date", "salary_display": "Salary", "status": "Status",
        }),
        use_container_width=True, hide_index=True,
    )

    ce1, ce2 = st.columns(2)
    export_cols = ["name", "mobile", "email", "role", "joining_date", "salary", "commission_percent", "status"]
    with ce1:
        st.download_button("⬇️ Export Excel", dataframe_to_excel_bytes(df[export_cols], "Staff", "Agents / Staff"),
                            file_name="staff.xlsx", use_container_width=True)
    with ce2:
        st.download_button("⬇️ Export PDF", dataframe_to_pdf_bytes(df[export_cols], "Agents / Staff"),
                            file_name="staff.pdf", use_container_width=True)

    st.markdown("---")
    options = {f"{row.id} — {row.name} ({row.role})": row.id for row in df.itertuples()}
    selected_label = st.selectbox("Select a staff member to edit / delete", list(options.keys()))
    selected_id = options[selected_label]
    _render_detail(tenant_id, selected_id, actor_id, is_demo)

    st.markdown('</div>', unsafe_allow_html=True)


def _render_detail(tenant_id, staff_id, actor_id, is_demo):
    row = run_query("SELECT * FROM staff WHERE id = ? AND tenant_id = ?", (staff_id, tenant_id), fetchone=True)
    if not row:
        st.warning("Staff record not found.")
        return

    if is_demo:
        st.info("This is the demo account — staff records can be viewed but not modified.")
        return

    tab_edit, tab_delete = st.tabs(["✏️ Edit", "🗑️ Delete"])

    with tab_edit:
        with st.form(f"edit_staff_{staff_id}"):
            e1, e2 = st.columns(2)
            with e1:
                name = st.text_input("Full Name", value=row["name"] or "")
                mobile = st.text_input("Mobile", value=row["mobile"] or "")
                email = st.text_input("Email", value=row["email"] or "")
                role = st.selectbox("Role", STAFF_ROLES, index=_safe_index(STAFF_ROLES, row["role"]))
            with e2:
                salary = st.number_input("Salary", min_value=0.0, step=1000.0, value=safe_float(row["salary"]))
                commission_percent = st.number_input("Commission %", min_value=0.0, step=0.5, value=safe_float(row["commission_percent"]))
                status = st.selectbox("Status", STAFF_STATUSES, index=_safe_index(STAFF_STATUSES, row["status"]))
            update_submitted = st.form_submit_button("Update Staff", type="primary", use_container_width=True)

        if update_submitted:
            run_query(
                """UPDATE staff SET name=?, mobile=?, email=?, role=?, salary=?, commission_percent=?, status=?
                   WHERE id = ? AND tenant_id = ?""",
                (name.strip(), mobile, email, role, safe_float(salary), safe_float(commission_percent), status, staff_id, tenant_id),
            )
            log_activity(tenant_id, "Staff Updated", f"Staff #{staff_id} updated", actor_user_id=actor_id)
            st.success("Staff record updated.")
            st.rerun()

    with tab_delete:
        st.warning("This will permanently delete this staff record. Any login access linked to it is not automatically removed.")
        confirm = st.checkbox("I confirm I want to delete this staff record", key=f"confirm_del_staff_{staff_id}")
        if st.button("Delete Staff", key=f"del_staff_{staff_id}", disabled=not confirm):
            run_query("DELETE FROM staff WHERE id = ? AND tenant_id = ?", (staff_id, tenant_id))
            log_activity(tenant_id, "Staff Deleted", f"Staff #{staff_id} deleted", actor_user_id=actor_id)
            st.success("Staff record deleted.")
            st.rerun()


def _render_logins(tenant_id, actor_id, is_demo):
    st.markdown('<div class="sn-card">', unsafe_allow_html=True)
    st.markdown("##### Create Login Access")

    if is_demo:
        st.info("The demo account cannot create new staff logins.")
    else:
        staff_df = run_df("SELECT id, name, mobile, email, role FROM staff WHERE tenant_id = ? ORDER BY name", (tenant_id,))
        if staff_df.empty:
            st.info("Add a staff record first, then come back here to create their login access.")
        else:
            staff_options = {f"{r.id} — {r.name}": r for r in staff_df.itertuples()}
            selected_label = st.selectbox("Staff Member", list(staff_options.keys()), key="login_staff_select")
            selected = staff_options[selected_label]

            with st.form("create_login_form", clear_on_submit=True):
                c1, c2 = st.columns(2)
                with c1:
                    username = st.text_input("Username *")
                    role = st.selectbox("Role", STAFF_ROLES, index=_safe_index(STAFF_ROLES, selected.role))
                with c2:
                    password = st.text_input("Password *", type="password")
                    confirm_password = st.text_input("Confirm Password *", type="password")
                submitted = st.form_submit_button("Create Login", type="primary", use_container_width=True)

            if submitted:
                if password != confirm_password:
                    st.error("Passwords do not match.")
                elif len(password) < MIN_PASSWORD_LENGTH:
                    st.error(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
                else:
                    success, message, _ = auth.create_staff_login(
                        tenant_id, selected.id, selected.name, selected.mobile or "", selected.email or "",
                        username, password, role, actor_user_id=actor_id,
                    )
                    if success:
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)

    st.markdown("---")
    st.markdown("##### Existing Logins")
    logins_df = run_df(
        "SELECT id, full_name, username, role, is_active FROM users WHERE tenant_id = ? ORDER BY id DESC",
        (tenant_id,),
    )
    if logins_df.empty:
        st.info("No staff logins created yet.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    display_df = logins_df.copy()
    display_df["Status"] = display_df["is_active"].apply(lambda v: "Active" if v else "Revoked")
    st.dataframe(
        display_df[["id", "full_name", "username", "role", "Status"]].rename(columns={
            "id": "ID", "full_name": "Name", "username": "Username", "role": "Role",
        }),
        use_container_width=True, hide_index=True,
    )

    if not is_demo:
        active_logins = logins_df[logins_df["is_active"] == 1]
        if not active_logins.empty:
            revoke_options = {f"{r.id} — {r.full_name} ({r.username})": r.id for r in active_logins.itertuples()}
            revoke_label = st.selectbox("Select a login to revoke", list(revoke_options.keys()))
            revoke_id = revoke_options[revoke_label]
            confirm = st.checkbox("I confirm I want to revoke this login", key=f"confirm_revoke_{revoke_id}")
            if st.button("Revoke Access", disabled=not confirm):
                success, message = auth.revoke_staff_login(tenant_id, revoke_id, actor_user_id=actor_id)
                if success:
                    st.success(message)
                    st.rerun()
                else:
                    st.error(message)

    st.markdown('</div>', unsafe_allow_html=True)


def _safe_index(options, value):
    try:
        return options.index(value)
    except (ValueError, TypeError):
        return 0
