"""
payment_gateway.py
Online payment collection, fully isolated from the rest of the app.

IMPORTANT — read before enabling in production:
This module talks to the Razorpay Payment Links REST API using whatever
API Key ID / Key Secret is entered in Settings -> Payment Gateway. Those
must be REAL credentials from your own Razorpay merchant account (created
at https://dashboard.razorpay.com) — this software does not, and cannot,
supply working payment credentials on your behalf. Until real keys are
entered and "Enable Payment Gateway" is turned on in Settings, every
function here fails gracefully with a clear message and the app falls
back to manual payment recording (Payments module), which always works
regardless of gateway configuration.

This app never processes card/bank details itself — Razorpay hosts the
actual checkout page; only a payment LINK is generated and stored here.
Confirming that a payment actually arrived still happens manually today
(mark the deal's payment as recorded in the Payments module) because a
local desktop app has no public URL to receive Razorpay's webhook. If you
later host this app on a server with a public URL, wire a webhook handler
to auto-confirm payments instead.
"""

import requests
from requests.auth import HTTPBasicAuth

from database import run_query

RAZORPAY_PAYMENT_LINKS_URL = "https://api.razorpay.com/v1/payment_links"


def _get_gateway_settings(tenant_id):
    return run_query("SELECT * FROM company_settings WHERE tenant_id = ?", (tenant_id,), fetchone=True) or {}


def is_gateway_configured(tenant_id):
    settings = _get_gateway_settings(tenant_id)
    return bool(
        settings.get("payment_gateway_enabled")
        and settings.get("payment_gateway_key_id")
        and settings.get("payment_gateway_key_secret")
    )


def create_payment_link(tenant_id, amount, description, customer_name="", customer_email="", customer_contact="", reference_id=""):
    """
    Creates a Razorpay Payment Link for the given amount (in the account's
    base currency units, e.g. rupees — converted to paise for the API),
    using THIS tenant's own gateway credentials (never another tenant's).
    Returns (success: bool, result: dict|str) where result is either
    {"short_url": ..., "id": ...} on success, or an error message string.
    """
    settings = _get_gateway_settings(tenant_id)

    if not settings.get("payment_gateway_enabled"):
        return False, "Payment gateway is not enabled. Turn it on in Settings -> Payment Gateway."

    provider = settings.get("payment_gateway_provider") or "Razorpay"
    if provider != "Razorpay":
        return False, f"'{provider}' is not yet wired up - only Razorpay Payment Links are implemented. Contact SN Softech Solutions to add another provider."

    key_id = settings.get("payment_gateway_key_id") or ""
    key_secret = settings.get("payment_gateway_key_secret") or ""
    if not key_id or not key_secret:
        return False, "Payment gateway API Key ID / Key Secret are missing. Add your real Razorpay credentials in Settings -> Payment Gateway."

    if amount is None or amount <= 0:
        return False, "Amount must be greater than zero."

    payload = {
        "amount": int(round(float(amount) * 100)),  # Razorpay expects paise
        "currency": "INR",
        "description": description or "Real Estate Payment",
        "customer": {
            "name": customer_name or "",
            "email": customer_email or "",
            "contact": customer_contact or "",
        },
        "notify": {"sms": bool(customer_contact), "email": bool(customer_email)},
        "reference_id": str(reference_id) if reference_id else None,
    }

    try:
        resp = requests.post(
            RAZORPAY_PAYMENT_LINKS_URL,
            json=payload,
            auth=HTTPBasicAuth(key_id, key_secret),
            timeout=15,
        )
    except requests.exceptions.RequestException as e:
        return False, f"Could not reach Razorpay - check your internet connection. ({e})"

    if resp.status_code in (200, 201):
        data = resp.json()
        return True, {"short_url": data.get("short_url"), "id": data.get("id"), "status": data.get("status")}

    try:
        err = resp.json().get("error", {}).get("description", resp.text)
    except Exception:
        err = resp.text
    return False, f"Razorpay rejected the request ({resp.status_code}): {err}"
