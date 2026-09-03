"""
modules/auth_pages.py
Pre-login screen: Sign In / Sign Up / Forgot Password. Nothing else in the
app renders before this — see app.py's main() gate on session_state.logged_in.
"""

import streamlit as st

from config import APP_NAME, APP_ICON, DEMO_USERNAME, DEMO_PASSWORD_DISPLAY
import auth


def render():
    st.markdown(
        f"""<div style="text-align:center;padding:18px 0 6px 0;">
                <h1 style="margin-bottom:0;">{APP_ICON} {APP_NAME}</h1>
                <p style="color:#64748B;font-size:14px;">Multi-tenant Real Estate CRM & Business Management</p>
            </div>""",
        unsafe_allow_html=True,
    )

    col = st.columns([1, 2, 1])[1]
    with col:
        tab_signin, tab_signup, tab_forgot = st.tabs(["Sign In", "Sign Up", "Forgot Password"])

        with tab_signin:
            _render_signin()

        with tab_signup:
            _render_signup()

        with tab_forgot:
            _render_forgot()


def _render_signin():
    with st.form("signin_form"):
        identifier = st.text_input("Username or Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign In", use_container_width=True, type="primary")

    if submitted:
        if not identifier or not password:
            st.error("Please enter both username/email and password.")
        else:
            success, message, user = auth.login_user(identifier, password)
            if success:
                st.session_state.logged_in = True
                st.session_state.user = user
                st.session_state.page = "dashboard"
                st.rerun()
            else:
                st.error(message)

    st.caption(f"Want to explore first? Use the demo login — username `{DEMO_USERNAME}`, password `{DEMO_PASSWORD_DISPLAY}`.")


def _render_signup():
    st.caption("Create your agency's account. No free trial — activate a Monthly or Yearly license key after signup.")
    with st.form("signup_form"):
        company_name = st.text_input("Company / Agency Name")
        full_name = st.text_input("Your Full Name")
        mobile = st.text_input("Mobile Number")
        email = st.text_input("Email Address")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        confirm_password = st.text_input("Confirm Password", type="password")
        submitted = st.form_submit_button("Create Account", use_container_width=True, type="primary")

    if submitted:
        errors = auth.validate_signup(full_name, mobile, email, username, password, confirm_password, company_name)
        if errors:
            for e in errors:
                st.error(e)
        else:
            success, message, _ = auth.signup_user(company_name, full_name, mobile, email, username, password)
            if success:
                st.success(f"{message} Switch to the Sign In tab to log in.")
            else:
                st.error(message)


def _render_forgot():
    with st.form("forgot_password_form"):
        email = st.text_input("Registered Email Address")
        new_password = st.text_input("New Password", type="password")
        confirm_password = st.text_input("Confirm New Password", type="password")
        submitted = st.form_submit_button("Reset Password", use_container_width=True, type="primary")

    if submitted:
        if not email or not new_password or not confirm_password:
            st.error("Please fill in all fields.")
        else:
            success, message = auth.reset_password_by_email(email, new_password, confirm_password)
            if success:
                st.success(message)
            else:
                st.error(message)
