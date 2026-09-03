"""
app.py
Main entry point for SN Real Estate Management System.
Handles: page config, DB init, session/auth gating, license gating,
sidebar navigation, and dispatch to feature modules.

MULTI-TENANT: every logged-in user (except the platform Super Admin) has
a `tenant_id` on their own users row, set at signup (auth.signup_user) or
staff-login creation (auth.create_staff_login). That tenant_id is resolved
ONCE per request, from the authenticated session — never from a URL
parameter, form field, or anything else the browser could tamper with —
and is the ONLY value passed into every module's data queries.
"""

import streamlit as st
import traceback

from config import APP_NAME, APP_FOOTER, APP_ICON, MENU_ITEMS, CURRENCIES, ROLE_MENU_ACCESS
from database import init_db, run_query
from style import CUSTOM_CSS
from license import get_access_status
from demo_data import load_demo_data
from auth import is_demo_tenant

from modules import (
    auth_pages, dashboard, properties, customers, leads, site_visits,
    deals, payments, expenses, staff, reports, kpi_analytics, followups,
    settings_page, license_page, super_admin,
)

st.set_page_config(page_title=APP_NAME, page_icon=APP_ICON, layout="wide", initial_sidebar_state="expanded")
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Startup: make sure the database exists (never destroys existing data)
# ---------------------------------------------------------------------------
try:
    init_db()
except Exception as e:
    st.error("A critical error occurred while initializing the database.")
    st.code(str(e))
    st.stop()

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user" not in st.session_state:
    st.session_state.user = None
if "page" not in st.session_state:
    st.session_state.page = "dashboard"


def get_company_settings(tenant_id):
    """Every tenant has its OWN company_settings row — this is never a
    shared/global lookup, so one tenant's branding/currency/SMTP config
    can never bleed into another's."""
    try:
        settings = run_query("SELECT * FROM company_settings WHERE tenant_id = ?", (tenant_id,), fetchone=True)
        return settings or {}
    except Exception:
        return {}


def sidebar_menu_css(menu_items, active_key):
    """
    Generates per-button multicolour CSS for the sidebar navigation.
    Each menu button gets its own gradient (from MENU_ITEMS in config.py),
    a matching hover glow, and the currently active page gets a bright
    left-accent + subtle glow so it's obviously selected.
    Targets buttons via the stable `.st-key-nav_<key>` class Streamlit
    attaches to each widget's container (based on the `key=` passed to
    st.sidebar.button), so styling stays correct regardless of ordering.
    """
    rules = []
    for icon, label, key, color in menu_items:
        is_active = key == active_key
        selector = f'section[data-testid="stSidebar"] .st-key-nav_{key} button'
        active_css = (
            f"border-left: 4px solid #FFFFFF !important; "
            f"box-shadow: 0 0 0 1px rgba(255,255,255,0.55), 0 6px 16px rgba(0,0,0,0.30) !important; "
            f"filter: brightness(1.1);"
            if is_active else ""
        )
        rules.append(f"""
            {selector} {{
                background: linear-gradient(135deg, {color}E6, {color}) !important;
                color: #FFFFFF !important;
                border: none;
                {active_css}
            }}
            {selector}:hover {{
                filter: brightness(1.15);
                box-shadow: 0 4px 14px {color}AA !important;
            }}
            {selector}:disabled {{
                background: linear-gradient(135deg, #94A3B8, #64748B) !important;
                color: #E2E8F0 !important;
                opacity: 0.6;
            }}
        """)
    return "<style>" + "".join(rules) + "</style>"


def allowed_menu_keys(role):
    """Returns the list of menu keys this role can see, or None for full access."""
    return ROLE_MENU_ACCESS.get(role, ROLE_MENU_ACCESS["Staff"])


def render_sidebar(access_granted, role, company_name):
    allowed = allowed_menu_keys(role)
    visible_items = MENU_ITEMS if allowed is None else [m for m in MENU_ITEMS if m[2] in allowed]

    st.sidebar.markdown(sidebar_menu_css(visible_items, st.session_state.page), unsafe_allow_html=True)
    st.sidebar.markdown(
        f"""<div class="sn-sidebar-brand">
                <h2>🏠 {company_name or APP_NAME}</h2>
                <span>{APP_FOOTER}</span>
            </div>""",
        unsafe_allow_html=True,
    )
    if role != "Admin":
        st.sidebar.markdown(
            f'<p style="color:#94A3B8;text-align:center;font-size:12px;margin-top:-8px;margin-bottom:12px;">Signed in as {role}</p>',
            unsafe_allow_html=True,
        )

    for icon, label, key, color in visible_items:
        disabled = (not access_granted) and key not in ("license", "logout", "settings", "super_admin")
        if st.sidebar.button(f"{icon}  {label}", key=f"nav_{key}", use_container_width=True, disabled=disabled):
            if key == "logout":
                for k in ("logged_in", "user"):
                    st.session_state[k] = False if k == "logged_in" else None
                st.session_state.page = "dashboard"
                st.rerun()
            else:
                st.session_state.page = key
                st.rerun()


def render_subscription_banner(status):
    """Called only when access is already granted (i.e. status == "Active"),
    since the "Unlicensed"/"Expired"/"Suspended"/"Cancelled" cases are
    blocked earlier. Shows a renewal reminder as expiry approaches."""
    if status["status"] == "Active" and status.get("renewal_due_soon"):
        st.markdown(f'<div class="sn-banner sn-banner-warn">🔐 {status["message"]}. Renew soon with a new license key to avoid interruption.</div>', unsafe_allow_html=True)


def main():
    if not st.session_state.logged_in or not st.session_state.user:
        auth_pages.render()
        return

    user = st.session_state.user
    role = user.get("role") or "Admin"

    # ------------------------------------------------------------------
    # Super Admin: platform-level, NOT tied to any tenant. Never resolves
    # a tenant_id, never touches business data, never sees the license
    # gate (a platform admin has no subscription of its own).
    # ------------------------------------------------------------------
    if role == "Super Admin":
        render_sidebar(access_granted=True, role=role, company_name="SN Softech — Platform Admin")
        st.markdown(
            f"""<div class="sn-topbar" style="background:linear-gradient(90deg,#0F172A,#334155);">
                    <div><h1>🛡️ SN Softech Solutions — Platform Admin</h1>
                    <p>Signed in as {user['full_name']}</p></div>
                </div>""",
            unsafe_allow_html=True,
        )
        page = st.session_state.page
        try:
            super_admin.render(actor_id=user["id"])
        except Exception:
            st.error("Something went wrong loading the Super Admin panel.")
            with st.expander("Technical details"):
                st.code(traceback.format_exc())
        st.markdown(f'<div class="sn-footer">{APP_FOOTER}</div>', unsafe_allow_html=True)
        return

    # ------------------------------------------------------------------
    # Normal tenant users (Admin / Manager / Sales Executive / Accountant
    # / Staff): resolve tenant_id from the authenticated session ONLY.
    # ------------------------------------------------------------------
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        st.error("This account isn't linked to a business. Please contact support.")
        st.stop()

    status = get_access_status(tenant_id)
    settings = get_company_settings(tenant_id)
    currency_symbol = CURRENCIES.get(settings.get("currency", "INR (₹)"), "₹")
    date_format = settings.get("date_format", "DD-MM-YYYY")
    company_name = settings.get("company_name") or APP_NAME

    render_sidebar(status["access_granted"], role, company_name)

    # Role-based page guard — if the current page isn't allowed for this
    # role (e.g. a bookmarked/stale session_state page after a role change),
    # silently fall back to the dashboard instead of showing a locked page.
    allowed = allowed_menu_keys(role)
    if allowed is not None and st.session_state.page not in allowed:
        st.session_state.page = "dashboard"

    demo_tag = " · DEMO ACCOUNT" if is_demo_tenant(tenant_id) else ""
    st.markdown(
        f"""<div class="sn-topbar">
                <div><h1>{APP_ICON} {company_name}</h1>
                <p>Welcome back, {user['full_name']} ({role}){demo_tag}</p></div>
                <div style="text-align:right;">
                    <p style="font-weight:700;">{status['status'].upper()}</p>
                </div>
            </div>""",
        unsafe_allow_html=True,
    )

    # ---------------- Hard gate: no active subscription = no access ----------------
    if not status["access_granted"]:
        license_page.render(tenant_id, user, blocking=True)
        st.markdown(f'<div class="sn-footer">{settings.get("footer_text") or APP_FOOTER}</div>', unsafe_allow_html=True)
        return

    render_subscription_banner(status)

    page = st.session_state.page

    try:
        if page == "dashboard":
            dashboard.render(tenant_id, currency_symbol, date_format)
        elif page == "properties":
            properties.render(tenant_id, currency_symbol, date_format)
        elif page == "customers":
            customers.render(tenant_id, currency_symbol, date_format)
        elif page == "leads":
            leads.render(tenant_id, currency_symbol, date_format)
        elif page == "site_visits":
            site_visits.render(tenant_id, currency_symbol, date_format)
        elif page == "deals":
            deals.render(tenant_id, currency_symbol, date_format)
        elif page == "payments":
            payments.render(tenant_id, currency_symbol, date_format)
        elif page == "expenses":
            expenses.render(tenant_id, currency_symbol, date_format)
        elif page == "staff":
            staff.render(tenant_id, currency_symbol, date_format, actor_id=user["id"])
        elif page == "reports":
            reports.render(tenant_id, currency_symbol, date_format)
        elif page == "kpi":
            kpi_analytics.render(tenant_id, currency_symbol, date_format)
        elif page == "followups":
            followups.render(tenant_id, currency_symbol, date_format)
        elif page == "settings":
            settings_page.render(tenant_id, currency_symbol, date_format, user)
            if not is_demo_tenant(tenant_id):
                st.markdown("---")
                if st.button("🎲 Load Demo Data (adds sample records for testing)"):
                    with st.spinner("Generating demo data..."):
                        load_demo_data(tenant_id)
                    st.success("Demo data loaded successfully. Explore the Dashboard and other modules!")
                    st.rerun()
        elif page == "license":
            license_page.render(tenant_id, user, blocking=False)
        else:
            dashboard.render(tenant_id, currency_symbol, date_format)
    except Exception as e:
        st.error("Something went wrong while loading this section. Your data is safe.")
        with st.expander("Technical details (for support)"):
            st.code(traceback.format_exc())

    st.markdown(f'<div class="sn-footer">{settings.get("footer_text") or APP_FOOTER}</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()
