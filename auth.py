"""
auth.py
Authentication logic, fully separated from UI and from licensing.
Uses PBKDF2-HMAC-SHA256 (via Python's hashlib, no extra dependency risk)
with a random per-user salt for password hashing — passwords are never
stored in plain text.

MULTI-TENANT: signup_user() creates a new tenant (one row in `tenants`)
plus its first Admin user, tied together via users.tenant_id. Every
subsequent staff login created for that business (create_staff_login)
shares the SAME tenant_id, which is how the whole app scopes data — see
database.py's module docstring.
"""

import re
import hashlib
import secrets
import datetime

from config import MIN_PASSWORD_LENGTH, DEMO_USERNAME
from database import run_query, log_activity

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
def _hash_password(password: str, salt: str = None) -> str:
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 200_000)
    return f"{salt}${digest.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, _ = stored_hash.split("$", 1)
    except ValueError:
        return False
    return secrets.compare_digest(_hash_password(password, salt), stored_hash)


# ---------------------------------------------------------------------------
# Demo account protection (Phase 13)
# ---------------------------------------------------------------------------
def is_demo_tenant(tenant_id):
    """True if this tenant is the protected demo/sample account. Used to
    block password changes, self-deletion, and configuration changes."""
    row = run_query("SELECT is_demo FROM tenants WHERE id = ?", (tenant_id,), fetchone=True)
    return bool(row and row.get("is_demo"))


def is_demo_user(user_id):
    row = run_query(
        "SELECT t.is_demo AS is_demo FROM users u JOIN tenants t ON u.tenant_id = t.id WHERE u.id = ?",
        (user_id,), fetchone=True,
    )
    return bool(row and row.get("is_demo"))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_signup(full_name, mobile, email, username, password, confirm_password, company_name=None):
    errors = []
    if company_name is not None and (not company_name or len(company_name.strip()) < 2):
        errors.append("Please enter your Company / Agency name.")
    if not full_name or len(full_name.strip()) < 2:
        errors.append("Please enter your full name.")
    if not mobile or not re.match(r"^\+?\d{7,15}$", mobile.strip()):
        errors.append("Please enter a valid mobile number.")
    if not email or not EMAIL_RE.match(email.strip()):
        errors.append("Please enter a valid email address.")
    if not username or len(username.strip()) < 3:
        errors.append("Username must be at least 3 characters.")
    if not password or len(password) < MIN_PASSWORD_LENGTH:
        errors.append(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if password != confirm_password:
        errors.append("Passwords do not match.")
    return errors


# ---------------------------------------------------------------------------
# Core actions
# ---------------------------------------------------------------------------
def signup_user(company_name, full_name, mobile, email, username, password):
    """
    Creates a brand-new TENANT (customer/agency) plus its first Admin user.
    Returns (success: bool, message: str, user_id or None).

    This is the ONLY place a new tenant is created in the whole app —
    every other account (staff logins) is added to an EXISTING tenant via
    create_staff_login() below.
    """
    existing = run_query(
        "SELECT id FROM users WHERE username = ? OR email = ?",
        (username.strip(), email.strip()),
        fetchone=True,
    )
    if existing:
        return False, "An account with this username or email already exists.", None

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    tenant_id = run_query(
        "INSERT INTO tenants (company_name, owner_name, mobile, email, is_demo, created_at) VALUES (?, ?, ?, ?, 0, ?)",
        (company_name.strip(), full_name.strip(), mobile.strip(), email.strip().lower(), now),
    )

    password_hash = _hash_password(password)
    user_id = run_query(
        """INSERT INTO users (tenant_id, full_name, mobile, email, username, password_hash, role, registration_date)
           VALUES (?, ?, ?, ?, ?, ?, 'Admin', ?)""",
        (tenant_id, full_name.strip(), mobile.strip(), email.strip().lower(), username.strip(), password_hash, now),
    )

    # Every tenant gets its own company_settings row (never a shared global
    # singleton — see database.py).
    run_query(
        "INSERT INTO company_settings (tenant_id, company_name) VALUES (?, ?)",
        (tenant_id, company_name.strip()),
    )

    # There is no free trial: every new tenant starts "Unlicensed" and has
    # no access to any module until a Monthly or Yearly license key is
    # activated from the License screen.
    run_query(
        """INSERT INTO licenses (tenant_id, license_key, registered_mobile, registered_email,
                                  activation_date, expiry_date, status, created_at)
           VALUES (?, NULL, ?, ?, NULL, NULL, 'Unlicensed', ?)""",
        (tenant_id, mobile.strip(), email.strip().lower(), now),
    )

    log_activity(tenant_id, "Signup", f"New tenant '{company_name}' created by {username}", actor_user_id=user_id)

    try:
        from notifications import send_welcome_email
        send_welcome_email(tenant_id, full_name, email, username)
    except Exception:
        pass  # email is best-effort and must never block signup

    return True, "Account created successfully. Please activate a Monthly or Yearly license key to start using the software.", user_id


def create_staff_login(tenant_id, staff_id, full_name, mobile, email, username, password, role, actor_user_id=None):
    """Creates a login account for a staff member, tied to an EXISTING
    tenant (business) — never creates a new tenant. Returns (success, message, user_id)."""
    if is_demo_tenant(tenant_id):
        return False, "The demo account cannot create new staff logins.", None

    errors = validate_signup(full_name, mobile, email, username, password, password)
    if errors:
        return False, " ".join(errors), None

    existing = run_query(
        "SELECT id FROM users WHERE username = ? OR email = ?",
        (username.strip(), email.strip()),
        fetchone=True,
    )
    if existing:
        return False, "An account with this username or email already exists.", None

    password_hash = _hash_password(password)
    reg_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    user_id = run_query(
        """INSERT INTO users (tenant_id, full_name, mobile, email, username, password_hash, role, staff_id, registration_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (tenant_id, full_name.strip(), mobile.strip(), email.strip().lower(), username.strip(), password_hash,
         role, staff_id, reg_date),
    )
    log_activity(tenant_id, "Create Staff Login", f"Login created for {username} ({role})",
                 actor_user_id=actor_user_id)
    return True, f"Login access created for {full_name} ({role}).", user_id


def revoke_staff_login(tenant_id, staff_user_id, actor_user_id=None):
    """Deactivates a staff member's login without deleting their account history."""
    if is_demo_tenant(tenant_id):
        return False, "The demo account cannot revoke staff logins."
    run_query("UPDATE users SET is_active = 0 WHERE id = ? AND tenant_id = ?", (staff_user_id, tenant_id))
    log_activity(tenant_id, "Revoke Staff Login", f"Login #{staff_user_id} deactivated", actor_user_id=actor_user_id)
    return True, "Login access revoked."


def login_user(identifier, password):
    """identifier = username or email. Returns (success, message, user dict or None)."""
    user = run_query(
        "SELECT * FROM users WHERE (username = ? OR email = ?) AND is_active = 1",
        (identifier.strip(), identifier.strip().lower()),
        fetchone=True,
    )
    if not user:
        return False, "No account found with that username/email.", None
    if not _verify_password(password, user["password_hash"]):
        return False, "Incorrect password.", None

    log_activity(user["tenant_id"], "Login", f"User {user['username']} logged in.", actor_user_id=user["id"])
    return True, "Login successful.", user


def change_password(user_id, old_password, new_password, confirm_password):
    user = run_query("SELECT * FROM users WHERE id = ?", (user_id,), fetchone=True)
    if not user:
        return False, "User not found."
    if is_demo_user(user_id):
        return False, "The demo account's password cannot be changed."
    if not _verify_password(old_password, user["password_hash"]):
        return False, "Current password is incorrect."
    if len(new_password) < MIN_PASSWORD_LENGTH:
        return False, f"New password must be at least {MIN_PASSWORD_LENGTH} characters."
    if new_password != confirm_password:
        return False, "New passwords do not match."

    run_query("UPDATE users SET password_hash = ? WHERE id = ?", (_hash_password(new_password), user_id))
    log_activity(user["tenant_id"], "Change Password", "Password changed successfully.", actor_user_id=user_id)

    try:
        from notifications import send_email
        send_email(user["tenant_id"], user["email"], "Your password was changed",
                   f"<p>Hi {user['full_name']},</p><p>Your SN Real Estate Management System password was just changed. "
                   f"If this wasn't you, please contact support immediately.</p>")
    except Exception:
        pass

    return True, "Password updated successfully."


def reset_password_by_email(email, new_password, confirm_password):
    """Simplified 'Forgot Password' flow appropriate for a local/offline app:
    verifies the account exists by email, then sets a new password.
    (For production with real email delivery, wire in an OTP/email-link service here.)"""
    user = run_query("SELECT * FROM users WHERE email = ?", (email.strip().lower(),), fetchone=True)
    if not user:
        return False, "No account found with that email address."
    if user["username"] == DEMO_USERNAME or is_demo_user(user["id"]):
        return False, "The demo account's password cannot be reset."
    if len(new_password) < MIN_PASSWORD_LENGTH:
        return False, f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if new_password != confirm_password:
        return False, "Passwords do not match."

    run_query("UPDATE users SET password_hash = ? WHERE id = ?", (_hash_password(new_password), user["id"]))
    log_activity(user["tenant_id"], "Password Reset", "Password reset via Forgot Password flow.", actor_user_id=user["id"])
    return True, "Password reset successfully. You can now log in."
