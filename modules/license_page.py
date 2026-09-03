"""
modules/license_page.py
License / subscription screen. Called both as a blocking hard-gate (no
other module reachable until access is restored) and as a normal
informational page reachable from the sidebar for an already-active tenant.
"""

import streamlit as st

from config import LICENSE_PLANS, PLAN_PRICING
import license as license_mod


def render(tenant_id, user, blocking):
    status = license_mod.get_access_status(tenant_id)

    if blocking:
        st.markdown(
            '<div class="sn-section-title">🔒 Access Blocked</div>'
            '<div class="sn-section-sub">Activate a license key to unlock the full application.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="sn-section-title">🔐 License & Subscription</div>'
            '<div class="sn-section-sub">View your subscription status and renew or activate a key here.</div>',
            unsafe_allow_html=True,
        )

    _render_status_banner(status)

    st.markdown('<div class="sn-card">', unsafe_allow_html=True)
    st.markdown("#### Activate a License Key")
    with st.form("license_activation_form"):
        license_key = st.text_input("License Key", placeholder="SNRE-YRL-XXXX-XXXX")
        col1, col2 = st.columns(2)
        with col1:
            mobile = st.text_input("Registered Mobile", value=user.get("mobile") or "")
        with col2:
            email = st.text_input("Registered Email", value=user.get("email") or "")
        submitted = st.form_submit_button("Activate License", use_container_width=True, type="primary")

    if submitted:
        if not license_key or not mobile or not email:
            st.error("Please fill in the license key, mobile and email.")
        else:
            success, message = license_mod.activate_license(tenant_id, license_key, mobile, email)
            if success:
                st.success(message)
                st.rerun()
            else:
                st.error(message)
    st.markdown('</div>', unsafe_allow_html=True)

    _render_plans_comparison()


def _render_status_banner(status):
    if status["status"] == "Active" and not status.get("renewal_due_soon"):
        css_class = "sn-banner-ok"
        icon = "✅"
    elif status["status"] == "Active" and status.get("renewal_due_soon"):
        css_class = "sn-banner-warn"
        icon = "⚠️"
    else:
        css_class = "sn-banner-danger"
        icon = "🚫"

    st.markdown(f'<div class="sn-banner {css_class}">{icon} {status["message"]}</div>', unsafe_allow_html=True)


def _render_plans_comparison():
    st.markdown('<div class="sn-card">', unsafe_allow_html=True)
    st.markdown("#### Available Plans")
    cols = st.columns(len(LICENSE_PLANS))
    for col, (plan_name, validity_days) in zip(cols, LICENSE_PLANS.items()):
        price = PLAN_PRICING.get(plan_name, 0)
        with col:
            st.markdown(
                f"""<div style="border:1px solid #E2E8F0;border-radius:12px;padding:16px;text-align:center;">
                        <h4 style="margin:0;">{plan_name}</h4>
                        <p style="font-size:22px;font-weight:800;margin:8px 0;">₹{price:,.0f}</p>
                        <p style="color:#64748B;font-size:13px;margin:0;">{validity_days} days validity</p>
                    </div>""",
                unsafe_allow_html=True,
            )
    st.caption("Contact SN Softech Solutions to purchase a license key for your preferred plan.")
    st.markdown('</div>', unsafe_allow_html=True)
