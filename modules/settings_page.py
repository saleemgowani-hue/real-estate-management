"""
modules/settings_page.py
Tenant-scoped settings: company profile, email/notifications, payment
gateway, backup & restore (SQLite only), and account (password change).
"""

import os

import streamlit as st

from config import CURRENCIES, DATE_FORMATS, THEMES, ASSETS_DIR
from database import run_query, log_activity, backup_database, restore_database
from auth import is_demo_tenant, is_demo_user, change_password
from notifications import send_test_email
from db_config import BACKEND


def render(tenant_id, currency_symbol, date_format, user):
    st.markdown(
        '<div class="sn-section-title">⚙️ Settings</div>'
        '<div class="sn-section-sub">Manage your company profile, integrations and account.</div>',
        unsafe_allow_html=True,
    )

    settings = run_query("SELECT * FROM company_settings WHERE tenant_id = ?", (tenant_id,), fetchone=True) or {}
    demo_tenant = is_demo_tenant(tenant_id)

    tab_company, tab_email, tab_payment, tab_backup, tab_account = st.tabs(
        ["🏢 Company Profile", "📧 Email / Notifications", "💳 Payment Gateway", "💾 Backup & Restore", "👤 Account"]
    )

    with tab_company:
        _render_company_profile(tenant_id, settings, demo_tenant, user)
    with tab_email:
        _render_email_settings(tenant_id, settings, demo_tenant, user)
    with tab_payment:
        _render_payment_gateway(tenant_id, settings, demo_tenant, user)
    with tab_backup:
        _render_backup_restore(tenant_id, demo_tenant, user)
    with tab_account:
        _render_account(user)


def _render_company_profile(tenant_id, settings, demo_tenant, user):
    st.markdown('<div class="sn-card">', unsafe_allow_html=True)
    if demo_tenant:
        st.info("This is the demo account. Company profile changes are disabled.")

    with st.form("company_profile_form"):
        company_name = st.text_input("Company Name", value=settings.get("company_name") or "")
        address = st.text_area("Address", value=settings.get("address") or "")
        col1, col2 = st.columns(2)
        with col1:
            mobile = st.text_input("Mobile", value=settings.get("mobile") or "")
            website = st.text_input("Website", value=settings.get("website") or "")
        with col2:
            email = st.text_input("Email", value=settings.get("email") or "")
            gst_number = st.text_input("GST Number", value=settings.get("gst_number") or "")
        footer_text = st.text_input("Footer Text", value=settings.get("footer_text") or "")

        col3, col4, col5 = st.columns(3)
        currency_keys = list(CURRENCIES.keys())
        current_currency = settings.get("currency") or currency_keys[0]
        with col3:
            currency = st.selectbox(
                "Currency", currency_keys,
                index=currency_keys.index(current_currency) if current_currency in currency_keys else 0,
            )
        current_date_format = settings.get("date_format") or DATE_FORMATS[0]
        with col4:
            date_fmt = st.selectbox(
                "Date Format", DATE_FORMATS,
                index=DATE_FORMATS.index(current_date_format) if current_date_format in DATE_FORMATS else 0,
            )
        current_theme = settings.get("theme") or THEMES[0]
        with col5:
            theme = st.selectbox(
                "Theme", THEMES,
                index=THEMES.index(current_theme) if current_theme in THEMES else 0,
            )

        logo_file = st.file_uploader("Company Logo", type=["png", "jpg", "jpeg"])
        submitted = st.form_submit_button("Save Company Profile", use_container_width=True, type="primary")

    if submitted:
        if demo_tenant:
            st.error("The demo account's settings cannot be changed.")
        else:
            logo_path = settings.get("logo_path") or ""
            if logo_file is not None:
                ext = os.path.splitext(logo_file.name)[1] or ".png"
                logo_path = os.path.join(ASSETS_DIR, f"tenant_{tenant_id}_logo{ext}")
                with open(logo_path, "wb") as f:
                    f.write(logo_file.getbuffer())

            run_query(
                """UPDATE company_settings SET company_name=?, address=?, mobile=?, email=?, website=?,
                   gst_number=?, footer_text=?, currency=?, date_format=?, theme=?, logo_path=?
                   WHERE tenant_id=?""",
                (company_name, address, mobile, email, website, gst_number, footer_text,
                 currency, date_fmt, theme, logo_path, tenant_id),
            )
            log_activity(tenant_id, "Update Settings", "Company profile updated.", actor_user_id=user["id"])
            st.success("Company profile updated successfully.")
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


def _render_email_settings(tenant_id, settings, demo_tenant, user):
    st.markdown('<div class="sn-card">', unsafe_allow_html=True)
    if demo_tenant:
        st.info("This is the demo account. Email settings changes are disabled.")

    with st.form("email_settings_form"):
        smtp_enabled = st.checkbox("Enable Email Notifications (SMTP)", value=bool(settings.get("smtp_enabled")))
        col1, col2 = st.columns(2)
        with col1:
            smtp_host = st.text_input("SMTP Host", value=settings.get("smtp_host") or "")
            smtp_username = st.text_input("SMTP Username", value=settings.get("smtp_username") or "")
            smtp_from_email = st.text_input("From Email", value=settings.get("smtp_from_email") or "")
        with col2:
            smtp_port = st.number_input("SMTP Port", min_value=1, max_value=65535, value=int(settings.get("smtp_port") or 587))
            smtp_password = st.text_input("SMTP Password", value=settings.get("smtp_password") or "", type="password")
            smtp_from_name = st.text_input("From Name", value=settings.get("smtp_from_name") or "")
        submitted = st.form_submit_button("Save Email Settings", use_container_width=True, type="primary")

    if submitted:
        if demo_tenant:
            st.error("The demo account's settings cannot be changed.")
        else:
            run_query(
                """UPDATE company_settings SET smtp_enabled=?, smtp_host=?, smtp_port=?, smtp_username=?,
                   smtp_password=?, smtp_from_email=?, smtp_from_name=? WHERE tenant_id=?""",
                (int(smtp_enabled), smtp_host, int(smtp_port), smtp_username, smtp_password,
                 smtp_from_email, smtp_from_name, tenant_id),
            )
            log_activity(tenant_id, "Update Settings", "Email/SMTP settings updated.", actor_user_id=user["id"])
            st.success("Email settings updated successfully.")
            st.rerun()

    st.markdown("---")
    st.markdown("##### Send a Test Email")
    test_email_to = st.text_input("Send test email to", value=user.get("email") or "", key="test_email_to")
    if st.button("Send Test Email"):
        success, message = send_test_email(tenant_id, test_email_to)
        if success:
            st.success(message)
        else:
            st.error(message)
    st.markdown('</div>', unsafe_allow_html=True)


def _render_payment_gateway(tenant_id, settings, demo_tenant, user):
    st.markdown('<div class="sn-card">', unsafe_allow_html=True)
    if demo_tenant:
        st.info("This is the demo account. Payment gateway changes are disabled.")
    st.caption("Enter your OWN Razorpay merchant credentials from https://dashboard.razorpay.com — this app cannot supply working payment credentials on your behalf.")

    with st.form("payment_gateway_form"):
        payment_gateway_enabled = st.checkbox("Enable Payment Gateway", value=bool(settings.get("payment_gateway_enabled")))
        payment_gateway_provider = st.selectbox(
            "Provider", ["Razorpay"],
            index=0,
        )
        payment_gateway_key_id = st.text_input("API Key ID", value=settings.get("payment_gateway_key_id") or "")
        payment_gateway_key_secret = st.text_input(
            "API Key Secret", value=settings.get("payment_gateway_key_secret") or "", type="password"
        )
        submitted = st.form_submit_button("Save Payment Gateway Settings", use_container_width=True, type="primary")

    if submitted:
        if demo_tenant:
            st.error("The demo account's settings cannot be changed.")
        else:
            run_query(
                """UPDATE company_settings SET payment_gateway_enabled=?, payment_gateway_provider=?,
                   payment_gateway_key_id=?, payment_gateway_key_secret=? WHERE tenant_id=?""",
                (int(payment_gateway_enabled), payment_gateway_provider, payment_gateway_key_id,
                 payment_gateway_key_secret, tenant_id),
            )
            log_activity(tenant_id, "Update Settings", "Payment gateway settings updated.", actor_user_id=user["id"])
            st.success("Payment gateway settings updated successfully.")
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


def _render_backup_restore(tenant_id, demo_tenant, user):
    st.markdown('<div class="sn-card">', unsafe_allow_html=True)

    if BACKEND != "sqlite":
        st.info("This deployment runs on PostgreSQL — backups are handled by your hosting provider's database backup/export tools, not from here.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    st.markdown("##### Create Backup")
    if st.button("Create Backup"):
        try:
            dest = backup_database()
            with open(dest, "rb") as f:
                data = f.read()
            st.success(f"Backup created: {os.path.basename(dest)}")
            st.download_button("Download Backup", data=data, file_name=os.path.basename(dest), mime="application/octet-stream")
            log_activity(tenant_id, "Update Settings", "Database backup created.", actor_user_id=user["id"])
        except Exception as e:
            st.error(f"Backup failed: {e}")

    st.markdown("---")
    st.markdown("##### Restore from Backup")
    if demo_tenant:
        st.info("This is the demo account. Restore is disabled.")
    st.warning("Restoring OVERWRITES the entire live database, affecting every tenant on this installation. Proceed only if you are certain.")
    restore_file = st.file_uploader("Choose a backup .db file", type=["db"])
    confirm_restore = st.checkbox("I understand this will overwrite the current database and cannot be undone.")
    if st.button("Restore Database", disabled=demo_tenant):
        if not restore_file:
            st.error("Please choose a backup file to restore.")
        elif not confirm_restore:
            st.error("Please confirm you understand this action before restoring.")
        else:
            try:
                tmp_path = os.path.join(ASSETS_DIR, f"_restore_upload_{restore_file.name}")
                with open(tmp_path, "wb") as f:
                    f.write(restore_file.getbuffer())
                restore_database(tmp_path)
                os.remove(tmp_path)
                log_activity(tenant_id, "Update Settings", "Database restored from uploaded backup.", actor_user_id=user["id"])
                st.success("Database restored successfully. Please refresh the app.")
            except Exception as e:
                st.error(f"Restore failed: {e}")
    st.markdown('</div>', unsafe_allow_html=True)


def _render_account(user):
    st.markdown('<div class="sn-card">', unsafe_allow_html=True)
    st.markdown("##### Change Password")

    if is_demo_user(user["id"]):
        st.info("The demo account's password cannot be changed.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    with st.form("change_password_form"):
        old_password = st.text_input("Current Password", type="password")
        new_password = st.text_input("New Password", type="password")
        confirm_password = st.text_input("Confirm New Password", type="password")
        submitted = st.form_submit_button("Change Password", use_container_width=True, type="primary")

    if submitted:
        success, message = change_password(user["id"], old_password, new_password, confirm_password)
        if success:
            st.success(message)
        else:
            st.error(message)
    st.markdown('</div>', unsafe_allow_html=True)
