"""
notifications.py
Email notifications, fully isolated from the rest of the app. All sending
is best-effort: if SMTP isn't configured or a send fails, the caller's
action (signup, password change, license activation, etc.) must never be
blocked — every call site wraps this in try/except and ignores failures.

SMTP settings live in company_settings (Settings -> Email / Notifications).
Nothing else in the app should read smtplib directly — this is the one seam.
"""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from database import run_query
from config import APP_NAME, APP_FOOTER


def _get_smtp_settings(tenant_id):
    return run_query("SELECT * FROM company_settings WHERE tenant_id = ?", (tenant_id,), fetchone=True) or {}


def send_email(tenant_id, to_email, subject, html_body):
    """Low-level sender. Returns (success: bool, message: str). Reads THIS
    tenant's own SMTP configuration — every tenant has its own row in
    company_settings, so one tenant's email credentials never leak into
    another's send."""
    settings = _get_smtp_settings(tenant_id)

    if not settings.get("smtp_enabled"):
        return False, "Email notifications are not enabled. Configure SMTP in Settings → Email / Notifications."
    if not to_email:
        return False, "No recipient email address available."

    host = settings.get("smtp_host") or ""
    port = int(settings.get("smtp_port") or 587)
    username = settings.get("smtp_username") or ""
    password = settings.get("smtp_password") or ""
    from_email = settings.get("smtp_from_email") or username
    from_name = settings.get("smtp_from_name") or APP_NAME

    if not host or not username or not password or not from_email:
        return False, "SMTP settings are incomplete. Please fill in all fields in Settings → Email / Notifications."

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_email
    footer = f'<p style="color:#94A3B8;font-size:12px;margin-top:20px;">{APP_FOOTER}</p>'
    msg.attach(MIMEText(html_body + footer, "html"))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.starttls(context=context)
            server.login(username, password)
            server.sendmail(from_email, [to_email], msg.as_string())
        return True, "Email sent successfully."
    except Exception as e:
        return False, f"Failed to send email: {e}"


def send_test_email(tenant_id, to_email):
    return send_email(
        tenant_id, to_email, f"Test Email from {APP_NAME}",
        "<p>This is a test email confirming your SMTP settings are configured correctly.</p>",
    )


def send_welcome_email(tenant_id, full_name, to_email, username):
    return send_email(
        tenant_id, to_email, f"Welcome to {APP_NAME}",
        f"""<p>Hi {full_name},</p>
            <p>Your account (<b>{username}</b>) has been created successfully.</p>
            <p>To start using the software, activate a Monthly or Yearly license key from the
            🔐 License menu inside the app. If you don't have a key yet, contact SN Softech Solutions.</p>""",
    )


def send_license_activated_email(tenant_id, full_name, to_email, plan_type, expiry_date_str):
    return send_email(
        tenant_id, to_email, f"{plan_type} Subscription Activated",
        f"""<p>Hi {full_name},</p>
            <p>Your <b>{plan_type}</b> subscription is now active and valid until
            <b>{expiry_date_str}</b>. Thank you for subscribing to {APP_NAME}.</p>""",
    )


def send_followup_reminder_email(tenant_id, to_email, recipient_name, note):
    return send_email(
        tenant_id, to_email, "Follow-up from your Real Estate Agent",
        f"""<p>Hi {recipient_name},</p>
            <p>{note}</p>
            <p>Feel free to reach out if you have any questions.</p>""",
    )
