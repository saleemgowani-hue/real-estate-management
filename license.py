"""
license.py
License / subscription (Monthly / Yearly) lifecycle, kept completely
separate from auth.py and the UI. There is NO free trial: a brand-new
account is "Unlicensed" and has zero access to any module until a valid
key is activated.

Design note: `validate_license_key()` is the single seam where an online
license-server/API call would be inserted later (e.g. POST the key +
device fingerprint to a licensing endpoint and trust its response instead
of the local `license_keys` table). Nothing else in the app needs to change
if that seam is swapped out.

Each license key is single-use: activating it marks it "Used" and ties it
to the activating user, exactly like a real sellable subscription key.
"""

import datetime

from config import LICENSE_PLANS, DEFAULT_PLAN, RENEWAL_REMINDER_DAYS, DEMO_VALID_KEYS, PLAN_PRICING
from database import run_query, log_activity

DATE_FMT = "%Y-%m-%d %H:%M:%S"


def _parse(dt_str):
    if not dt_str:
        return None
    for fmt in (DATE_FMT, "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(dt_str, fmt)
        except ValueError:
            continue
    return None


def get_license_record(tenant_id):
    return run_query(
        "SELECT * FROM licenses WHERE tenant_id = ? ORDER BY id DESC LIMIT 1",
        (tenant_id,),
        fetchone=True,
    )


def get_access_status(tenant_id):
    """
    Returns a dict describing whether the user currently has access to the
    protected application, and all the display information the UI needs:

    {
        "access_granted": bool,
        "status": "Unlicensed" | "Active" | "Expired" | "Invalid" | "Suspended",
        "plan_type": "Monthly" | "Yearly" | None,
        "days_remaining": int,
        "message": str,
        "expiry_date": datetime or None,
        "renewal_due_soon": bool,
    }
    """
    record = get_license_record(tenant_id)
    now = datetime.datetime.now()

    if not record:
        return {
            "access_granted": False, "status": "Unlicensed", "plan_type": None,
            "days_remaining": 0,
            "message": "No license found for this account. Please activate a Monthly or Yearly license key to continue.",
            "expiry_date": None, "renewal_due_soon": False,
        }

    status = record["status"]
    plan_type = record["plan_type"] or DEFAULT_PLAN

    if status == "Active":
        expiry = _parse(record["expiry_date"])
        if expiry and now <= expiry:
            days_remaining = (expiry.date() - now.date()).days
            reminder_window = RENEWAL_REMINDER_DAYS.get(plan_type, 15)
            return {
                "access_granted": True, "status": "Active", "plan_type": plan_type,
                "days_remaining": days_remaining,
                "message": f"License Active ({plan_type} Plan) — Valid Until: {expiry.strftime('%d-%m-%Y')} ({days_remaining} days remaining)",
                "expiry_date": expiry, "renewal_due_soon": days_remaining <= reminder_window,
            }
        else:
            run_query("UPDATE licenses SET status = 'Expired' WHERE id = ?", (record["id"],))
            return {
                "access_granted": False, "status": "Expired", "plan_type": plan_type,
                "days_remaining": 0,
                "message": f"Your {plan_type} subscription has expired. Please activate a new license key to continue.",
                "expiry_date": expiry, "renewal_due_soon": False,
            }

    if status == "Suspended":
        return {
            "access_granted": False, "status": "Suspended", "plan_type": plan_type,
            "days_remaining": 0, "message": "This account's license has been suspended. Please contact support.",
            "expiry_date": None, "renewal_due_soon": False,
        }

    if status == "Cancelled":
        return {
            "access_granted": False, "status": "Cancelled", "plan_type": plan_type,
            "days_remaining": 0, "message": "This subscription has been cancelled. Please activate a new license key to continue.",
            "expiry_date": None, "renewal_due_soon": False,
        }

    # "Unlicensed" (brand-new signup) and any legacy "Trial" rows from
    # before the free trial was removed are treated identically: no access
    # until a real key is activated.
    if status in ("Unlicensed", "Trial"):
        return {
            "access_granted": False, "status": "Unlicensed", "plan_type": None,
            "days_remaining": 0,
            "message": "No active subscription. Please activate a Monthly or Yearly license key to start using the software.",
            "expiry_date": None, "renewal_due_soon": False,
        }

    # status == "Expired" or anything else unrecognized
    return {
        "access_granted": False, "status": "Expired", "plan_type": plan_type,
        "days_remaining": 0, "message": "Your access has expired. Please activate a subscription to continue.",
        "expiry_date": _parse(record["expiry_date"]), "renewal_due_soon": False,
    }


def validate_license_key(license_key: str):
    """
    Returns (is_valid: bool, plan_type: str|None, reason: str).

    Checks, in order: the always-valid demo/QA keys, then the issued
    license_keys pool (must exist and be Unused). Replace this function's
    body with a real API call for production if you move to an online
    license server.
    """
    key = (license_key or "").strip().upper()
    if not key:
        return False, None, "Please enter a license key."

    if key in DEMO_VALID_KEYS:
        return True, DEMO_VALID_KEYS[key], "Demo/QA key."

    row = run_query("SELECT * FROM license_keys WHERE license_key = ?", (key,), fetchone=True)
    if not row:
        return False, None, "This license key was not found. Please check for typos."
    if row["status"] == "Used":
        return False, None, "This license key has already been used to activate an account."
    return True, row["plan_type"], "Valid, unused key."


def activate_license(tenant_id, license_key, mobile, email, payment_gateway_transaction_id=None):
    """Returns (success: bool, message: str)."""
    key = (license_key or "").strip().upper()
    is_valid, plan_type, reason = validate_license_key(key)
    if not is_valid:
        return False, reason

    if plan_type not in LICENSE_PLANS:
        return False, "This key's plan type is not recognized."

    now = datetime.datetime.now()
    now_str = now.strftime(DATE_FMT)
    expiry = now + datetime.timedelta(days=LICENSE_PLANS[plan_type])
    amount = PLAN_PRICING.get(plan_type)

    existing = get_license_record(tenant_id)
    if existing:
        run_query(
            """UPDATE licenses SET license_key=?, plan_type=?, amount=?, registered_mobile=?, registered_email=?,
               activation_date=?, expiry_date=?, status='Active', payment_status='Paid',
               transaction_id=?, updated_at=? WHERE id=?""",
            (key, plan_type, amount, mobile, email, now_str, expiry.strftime(DATE_FMT),
             payment_gateway_transaction_id, now_str, existing["id"]),
        )
    else:
        run_query(
            """INSERT INTO licenses (tenant_id, license_key, plan_type, amount, registered_mobile, registered_email,
                                      activation_date, expiry_date, status, payment_status, transaction_id,
                                      created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Active', 'Paid', ?, ?, ?)""",
            (tenant_id, key, plan_type, amount, mobile, email, now_str, expiry.strftime(DATE_FMT),
             payment_gateway_transaction_id, now_str, now_str),
        )

    # Mark the key as consumed (no-op for demo/QA keys, which aren't in the pool table)
    run_query(
        "UPDATE license_keys SET status = 'Used', used_by_tenant_id = ?, used_date = ? WHERE license_key = ? AND status = 'Unused'",
        (tenant_id, now_str, key),
    )

    log_activity(tenant_id, "License Activated", f"Key: {key} ({plan_type}), valid until {expiry.strftime('%d-%m-%Y')}")

    try:
        from notifications import send_license_activated_email
        tenant = run_query("SELECT owner_name, email FROM tenants WHERE id = ?", (tenant_id,), fetchone=True)
        if tenant:
            send_license_activated_email(tenant_id, tenant["owner_name"], tenant["email"], plan_type, expiry.strftime("%d-%m-%Y"))
    except Exception:
        pass

    return True, f"{plan_type} subscription activated successfully. Valid until {expiry.strftime('%d-%m-%Y')}."


def get_key_pool_summary():
    """Returns counts of unused/used keys per plan — used on the admin/license screen."""
    rows = run_query(
        "SELECT plan_type, status, COUNT(*) as c FROM license_keys GROUP BY plan_type, status",
        fetch=True,
    )
    summary = {plan: {"Unused": 0, "Used": 0} for plan in LICENSE_PLANS}
    for r in rows:
        if r["plan_type"] in summary:
            summary[r["plan_type"]][r["status"]] = r["c"]
    return summary
