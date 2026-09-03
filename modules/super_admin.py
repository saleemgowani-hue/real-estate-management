"""
modules/super_admin.py
Platform-level Super Admin panel (SN Softech Solutions only). Unlike every
other module, this one operates ACROSS ALL TENANTS by design — there is no
tenant_id to scope by, since the Super Admin is not a tenant user.
"""

import datetime

import streamlit as st

from config import LICENSE_PLANS, LICENSE_STATUSES
from database import run_query, run_df, log_activity
from license import get_key_pool_summary
from style import badge_html
from utils import fmt_date, fmt_currency, dataframe_to_excel_bytes

DATE_FMT = "%Y-%m-%d %H:%M:%S"


def render(actor_id):
    st.markdown(
        '<div class="sn-section-title">🛡️ Platform Administration</div>'
        '<div class="sn-section-sub">Manage every tenant, license and key on the SN Real Estate platform.</div>',
        unsafe_allow_html=True,
    )

    tab_overview, tab_tenants, tab_keys, tab_users = st.tabs(
        ["📊 Overview", "🏢 Tenants & Licenses", "🔑 License Keys", "👥 Users"]
    )

    with tab_overview:
        _render_overview()
    with tab_tenants:
        _render_tenants(actor_id)
    with tab_keys:
        _render_license_keys()
    with tab_users:
        _render_users()


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------
def _kpi_card(label, value, icon, color):
    st.markdown(
        f"""<div class="kpi-card" style="background:linear-gradient(135deg,{color}E6,{color});">
                <div class="kpi-label">{label}</div>
                <div class="kpi-value">{value}</div>
                <div class="kpi-icon">{icon}</div>
            </div>""",
        unsafe_allow_html=True,
    )


def _render_overview():
    total_tenants = run_query("SELECT COUNT(*) AS c FROM tenants", fetchone=True)["c"]
    active_subs = run_query("SELECT COUNT(*) AS c FROM licenses WHERE status = 'Active'", fetchone=True)["c"]
    total_users = run_query("SELECT COUNT(*) AS c FROM users WHERE tenant_id IS NOT NULL", fetchone=True)["c"]
    demo_tenants = run_query("SELECT COUNT(*) AS c FROM tenants WHERE is_demo = 1", fetchone=True)["c"]

    pool = get_key_pool_summary()
    total_unused = sum(v["Unused"] for v in pool.values())
    total_used = sum(v["Used"] for v in pool.values())

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _kpi_card("Total Tenants", total_tenants, "🏢", "#4F46E5")
    with c2:
        _kpi_card("Active Subscriptions", active_subs, "✅", "#10B981")
    with c3:
        _kpi_card("Total Users", total_users, "👥", "#0EA5E9")
    with c4:
        _kpi_card("Unused License Keys", total_unused, "🔑", "#F59E0B")

    c5, c6, c7 = st.columns(3)
    with c5:
        _kpi_card("Used License Keys", total_used, "📦", "#8B5CF6")
    with c6:
        _kpi_card("Demo/Sample Tenants", demo_tenants, "🎲", "#64748B")
    with c7:
        expired = run_query("SELECT COUNT(*) AS c FROM licenses WHERE status = 'Expired'", fetchone=True)["c"]
        _kpi_card("Expired Subscriptions", expired, "⌛", "#EF4444")

    st.markdown('<div class="sn-card">', unsafe_allow_html=True)
    st.markdown("#### License Key Pool by Plan")
    pool_df = _pool_summary_df(pool)
    st.dataframe(pool_df, use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)


def _pool_summary_df(pool):
    import pandas as pd
    rows = [{"Plan": plan, "Unused": counts["Unused"], "Used": counts["Used"],
              "Total": counts["Unused"] + counts["Used"]} for plan, counts in pool.items()]
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tenants & Licenses
# ---------------------------------------------------------------------------
def _tenants_with_license_df():
    df = run_df(
        """SELECT t.id, t.company_name, t.owner_name, t.mobile, t.email, t.is_demo, t.created_at,
                  l.status AS license_status, l.plan_type, l.expiry_date
           FROM tenants t
           LEFT JOIN licenses l ON l.id = (SELECT MAX(id) FROM licenses WHERE tenant_id = t.id)
           ORDER BY t.id DESC"""
    )
    return df


def _render_tenants(actor_id):
    st.markdown('<div class="sn-card">', unsafe_allow_html=True)
    st.markdown("#### All Tenants")

    df = _tenants_with_license_df()
    if df.empty:
        st.info("No tenants yet.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    search = st.text_input("🔍 Search by company / owner / email")
    view = df.copy()
    if search:
        s = search.lower()
        mask = (
            view["company_name"].fillna("").str.lower().str.contains(s)
            | view["owner_name"].fillna("").str.lower().str.contains(s)
            | view["email"].fillna("").str.lower().str.contains(s)
        )
        view = view[mask]

    view = view.copy()
    view["Demo"] = view["is_demo"].apply(lambda v: "Yes" if v else "No")
    view["Created"] = view["created_at"].apply(lambda v: fmt_date(v))
    view["Expiry"] = view["expiry_date"].apply(lambda v: fmt_date(v))
    view["license_status"] = view["license_status"].fillna("Unlicensed")

    st.dataframe(
        view[["id", "company_name", "owner_name", "mobile", "email", "Demo",
              "license_status", "plan_type", "Expiry", "Created"]].rename(columns={
            "id": "ID", "company_name": "Company", "owner_name": "Owner", "mobile": "Mobile",
            "email": "Email", "license_status": "License Status", "plan_type": "Plan",
        }),
        use_container_width=True, hide_index=True,
    )
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="sn-card">', unsafe_allow_html=True)
    st.markdown("#### Tenant License Actions")

    options = {f"{row.id} — {row.company_name}": row.id for row in df.itertuples()}
    selected_label = st.selectbox("Select a tenant", list(options.keys()))
    tenant_id = options[selected_label]
    _render_tenant_actions(tenant_id, actor_id)
    st.markdown('</div>', unsafe_allow_html=True)


def _render_tenant_actions(tenant_id, actor_id):
    tenant = run_query("SELECT * FROM tenants WHERE id = ?", (tenant_id,), fetchone=True)
    if not tenant:
        st.warning("Tenant not found.")
        return
    is_demo = bool(tenant["is_demo"])

    license_row = run_query(
        "SELECT * FROM licenses WHERE tenant_id = ? ORDER BY id DESC LIMIT 1", (tenant_id,), fetchone=True
    )

    if is_demo:
        st.info("🎲 This is the protected demo/sample tenant. Its license status is displayed for reference only and cannot be suspended or cancelled here.")

    dc1, dc2, dc3 = st.columns(3)
    with dc1:
        st.write(f"**Company:** {tenant['company_name']}")
        st.write(f"**Owner:** {tenant['owner_name'] or '-'}")
    with dc2:
        st.write(f"**Mobile:** {tenant['mobile'] or '-'}")
        st.write(f"**Email:** {tenant['email'] or '-'}")
    with dc3:
        if license_row:
            st.markdown(f"**License Status:** {badge_html(license_row['status'])}", unsafe_allow_html=True)
            st.write(f"**Plan:** {license_row['plan_type'] or '-'}")
        else:
            st.write("**License Status:** No license record found.")

    if license_row:
        lc1, lc2, lc3 = st.columns(3)
        with lc1:
            st.write(f"**License Key:** {license_row['license_key'] or '-'}")
        with lc2:
            st.write(f"**Activated:** {fmt_date(license_row['activation_date'])}")
        with lc3:
            st.write(f"**Expires:** {fmt_date(license_row['expiry_date'])}")
        st.write(f"**Amount:** {fmt_currency(license_row['amount'])} | **Payment Status:** {license_row['payment_status'] or '-'}")

    st.markdown("---")
    st.markdown("##### Change License Status")
    current_status = license_row["status"] if license_row else "Unlicensed"
    status_idx = LICENSE_STATUSES.index(current_status) if current_status in LICENSE_STATUSES else 0
    new_status = st.selectbox("New status", LICENSE_STATUSES, index=status_idx, key=f"status_sel_{tenant_id}")

    is_destructive = new_status in ("Suspended", "Cancelled")
    confirm = True
    if is_destructive:
        confirm = st.checkbox(
            f"I confirm I want to set this tenant's license status to '{new_status}'.",
            key=f"confirm_status_{tenant_id}",
        )

    if st.button("Update License Status", key=f"apply_status_{tenant_id}", disabled=is_destructive and not confirm):
        if is_demo and is_destructive:
            st.warning("The protected demo tenant cannot be suspended or cancelled.")
        else:
            now_str = datetime.datetime.now().strftime(DATE_FMT)
            if license_row:
                run_query(
                    "UPDATE licenses SET status = ?, updated_at = ? WHERE tenant_id = ?",
                    (new_status, now_str, tenant_id),
                )
            else:
                run_query(
                    "INSERT INTO licenses (tenant_id, status, created_at, updated_at) VALUES (?, ?, ?, ?)",
                    (tenant_id, new_status, now_str, now_str),
                )
            log_activity(
                tenant_id, "Super Admin: License Status Changed",
                f"Status set to '{new_status}' by Super Admin.", actor_user_id=actor_id,
            )
            st.success(f"License status updated to '{new_status}'.")
            st.rerun()

    st.markdown("---")
    st.markdown("##### Reactivate / Extend Subscription")
    with st.form(f"extend_license_{tenant_id}"):
        plan = st.selectbox("Plan to grant / extend by", list(LICENSE_PLANS.keys()), key=f"plan_sel_{tenant_id}")
        extend_submitted = st.form_submit_button("Reactivate & Extend Expiry", type="primary", use_container_width=True)

    if extend_submitted:
        now = datetime.datetime.now()
        current_expiry = _parse_dt(license_row["expiry_date"]) if license_row else None
        base = current_expiry if current_expiry and current_expiry > now else now
        new_expiry = base + datetime.timedelta(days=LICENSE_PLANS[plan])
        now_str = now.strftime(DATE_FMT)

        if license_row:
            run_query(
                """UPDATE licenses SET status = 'Active', plan_type = ?, activation_date = ?,
                       expiry_date = ?, updated_at = ? WHERE tenant_id = ?""",
                (plan, now_str, new_expiry.strftime(DATE_FMT), now_str, tenant_id),
            )
        else:
            run_query(
                """INSERT INTO licenses (tenant_id, plan_type, activation_date, expiry_date, status,
                       payment_status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'Active', 'Paid', ?, ?)""",
                (tenant_id, plan, now_str, new_expiry.strftime(DATE_FMT), now_str, now_str),
            )
        log_activity(
            tenant_id, "Super Admin: License Reactivated/Extended",
            f"{plan} plan granted, new expiry {new_expiry.strftime('%d-%m-%Y')}.", actor_user_id=actor_id,
        )
        st.success(f"License reactivated with the {plan} plan, valid until {new_expiry.strftime('%d-%m-%Y')}.")
        st.rerun()


def _parse_dt(value):
    if not value:
        return None
    for fmt in (DATE_FMT, "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(value, fmt)
        except (ValueError, TypeError):
            continue
    return None


# ---------------------------------------------------------------------------
# License Keys
# ---------------------------------------------------------------------------
def _render_license_keys():
    st.markdown('<div class="sn-card">', unsafe_allow_html=True)
    st.markdown("#### License Key Pool Summary")
    pool = get_key_pool_summary()
    st.dataframe(_pool_summary_df(pool), use_container_width=True, hide_index=True)
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<div class="sn-card">', unsafe_allow_html=True)
    st.markdown("#### All License Keys")

    fc1, fc2, fc3 = st.columns([2, 1, 1])
    with fc1:
        search = st.text_input("🔍 Search key")
    with fc2:
        f_status = st.selectbox("Status", ["All", "Unused", "Used"])
    with fc3:
        f_plan = st.selectbox("Plan", ["All"] + list(LICENSE_PLANS.keys()))

    sql = "SELECT * FROM license_keys WHERE 1=1"
    params = []
    if search:
        sql += " AND license_key LIKE ?"
        params.append(f"%{search}%")
    if f_status != "All":
        sql += " AND status = ?"
        params.append(f_status)
    if f_plan != "All":
        sql += " AND plan_type = ?"
        params.append(f_plan)
    sql += " ORDER BY id DESC"

    df = run_df(sql, tuple(params))
    if df.empty:
        st.info("No license keys match this filter.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    display_df = df.copy()
    display_df["used_date"] = display_df["used_date"].apply(lambda v: fmt_date(v))

    st.dataframe(
        display_df[["id", "license_key", "plan_type", "status", "used_by_tenant_id", "used_date"]].rename(columns={
            "id": "ID", "license_key": "Key", "plan_type": "Plan", "status": "Status",
            "used_by_tenant_id": "Used By Tenant ID", "used_date": "Used Date",
        }),
        use_container_width=True, hide_index=True,
    )

    st.download_button(
        "⬇️ Export Excel",
        dataframe_to_excel_bytes(df[["license_key", "plan_type", "status", "used_by_tenant_id", "used_date"]],
                                  "License Keys", "License Key Pool"),
        file_name="license_keys.xlsx", use_container_width=True,
    )
    st.markdown('</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
def _render_users():
    st.markdown('<div class="sn-card">', unsafe_allow_html=True)
    st.markdown("#### All Platform Users")

    df = run_df(
        """SELECT u.id, u.full_name, u.username, u.mobile, u.email, u.role, u.is_active,
                  u.registration_date, t.company_name
           FROM users u
           LEFT JOIN tenants t ON t.id = u.tenant_id
           ORDER BY u.id DESC"""
    )
    if df.empty:
        st.info("No users found.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    search = st.text_input("🔍 Search by name / username / email / company")
    view = df.copy()
    if search:
        s = search.lower()
        mask = (
            view["full_name"].fillna("").str.lower().str.contains(s)
            | view["username"].fillna("").str.lower().str.contains(s)
            | view["email"].fillna("").str.lower().str.contains(s)
            | view["company_name"].fillna("").str.lower().str.contains(s)
        )
        view = view[mask]

    view = view.copy()
    view["Status"] = view["is_active"].apply(lambda v: "Active" if v else "Inactive")
    view["Registered"] = view["registration_date"].apply(lambda v: fmt_date(v))
    view["company_name"] = view["company_name"].fillna("— Platform —")

    st.dataframe(
        view[["id", "full_name", "username", "mobile", "email", "role", "company_name", "Status", "Registered"]].rename(columns={
            "id": "ID", "full_name": "Name", "username": "Username", "mobile": "Mobile",
            "email": "Email", "role": "Role", "company_name": "Tenant / Company",
        }),
        use_container_width=True, hide_index=True,
    )
    st.markdown('</div>', unsafe_allow_html=True)
