"""
config.py
Centralized configuration for SN Real Estate Management System.
NOTHING in this project should hard-code a database path, trial length,
or license duration outside of this file.
"""

import os

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
DOCS_DIR = os.path.join(DATA_DIR, "documents")
IMAGES_DIR = os.path.join(DATA_DIR, "images")

for _d in (DATA_DIR, ASSETS_DIR, BACKUP_DIR, DOCS_DIR, IMAGES_DIR):
    os.makedirs(_d, exist_ok=True)

DB_PATH = os.path.join(DATA_DIR, "sn_realestate.db")

# ---------------------------------------------------------------------------
# App identity
# ---------------------------------------------------------------------------
APP_NAME = "SN Real Estate Management System"
APP_FOOTER = "Powered by SN Softech Solutions"
APP_ICON = "🏠"

# ---------------------------------------------------------------------------
# License / Subscription configuration (single source of truth)
# ---------------------------------------------------------------------------
# NOTE: There is no free trial. A brand-new account is created with status
# "Unlicensed" and has NO access to any module until a valid Monthly or
# Yearly license key is activated from the License screen.

# Subscription plans: plan name -> validity in days.
# To add a new plan (e.g. "Quarterly"), add one line here — nothing else
# in the app hard-codes a plan length.
LICENSE_PLANS = {
    "Monthly": 30,
    "Yearly": 365,
}
DEFAULT_PLAN = "Yearly"
LICENSE_VALIDITY_DAYS = LICENSE_PLANS[DEFAULT_PLAN]  # kept for backward compatibility

# Renewal reminder window (days before expiry to start showing the renewal banner).
# Monthly plans get a shorter/urgent window since the whole cycle is only 30 days.
RENEWAL_REMINDER_DAYS = {
    "Monthly": 5,
    "Yearly": 15,
}

# Prefix used for generated license keys, per plan — lets the validator and
# any human glancing at a key immediately tell which plan it belongs to.
KEY_PREFIX = {
    "Monthly": "SNRE-MON",
    "Yearly": "SNRE-YRL",
}

# A handful of always-valid demo/QA keys (not part of the sellable batches),
# useful for local testing without consuming an issued key.
DEMO_VALID_KEYS = {
    "SNRE-MON-DEMO-0000": "Monthly",
    "SNRE-YRL-DEMO-0000": "Yearly",
}

LICENSE_STATUSES = ["Unlicensed", "Active", "Expired", "Invalid", "Suspended", "Cancelled"]

# ---------------------------------------------------------------------------
# Protected demo account (Phase 13 of the SaaS spec)
# ---------------------------------------------------------------------------
DEMO_USERNAME = "demo"
DEMO_PASSWORD_DISPLAY = "Demo@12345"  # shown on the login screen so visitors can try it

# ---------------------------------------------------------------------------
# Platform-level Super Admin (SN Softech Solutions only). Not tied to any
# tenant. CHANGE THIS PASSWORD immediately after your first deployment —
# it is only a seed default, not a secret meant to ship to production as-is.
# For a real deployment, override via Streamlit secrets:
#   [super_admin]
#   username = "..."
#   password = "..."
# ---------------------------------------------------------------------------
SUPER_ADMIN_USERNAME = "superadmin"
SUPER_ADMIN_DEFAULT_PASSWORD = "ChangeMe@SuperAdmin123"

# Informational list price per plan — shown on the License screen and stored
# on the subscription record. Update these to your real pricing; the app
# does not derive them from anywhere else.
PLAN_PRICING = {
    "Monthly": 999,
    "Yearly": 9999,
}

# ---------------------------------------------------------------------------
# Session / security
# ---------------------------------------------------------------------------
SESSION_COOKIE_DAYS = 7  # "remember me" horizon (best-effort within one browser session)
MIN_PASSWORD_LENGTH = 6

# ---------------------------------------------------------------------------
# Domain enums (kept centralized so every module agrees on valid values)
# ---------------------------------------------------------------------------
PROPERTY_TYPES = [
    "Residential", "Commercial", "Plot/Land", "Apartment",
    "Villa", "Office", "Shop", "Warehouse", "Other",
]
LISTING_TYPES = ["Sale", "Rent"]
PROPERTY_STATUSES = ["Available", "Under Negotiation", "Sold", "Rented", "Hold", "Inactive"]
FURNISHED_STATUSES = ["Unfurnished", "Semi-Furnished", "Fully-Furnished"]
FACING_OPTIONS = ["North", "South", "East", "West", "North-East", "North-West", "South-East", "South-West"]

LEAD_STATUSES = ["New", "Contacted", "Follow-up", "Site Visit", "Negotiation", "Converted", "Lost"]
LEAD_SOURCES = ["Website", "Referral", "Walk-in", "Phone Call", "Social Media", "Advertisement", "Other"]

VISIT_STATUSES = ["Scheduled", "Completed", "Cancelled", "Rescheduled"]

DEAL_STATUSES = ["Negotiation", "Booked", "Completed", "Cancelled"]
PAYMENT_STATUSES = ["Pending", "Partial", "Paid"]

PAYMENT_MODES = ["Cash", "UPI", "Bank Transfer", "Cheque", "Other"]

EXPENSE_CATEGORIES = [
    "Office Rent", "Electricity", "Marketing", "Salary", "Travel",
    "Maintenance", "Advertisement", "Commission", "Other",
]

STAFF_ROLES = ["Admin", "Manager", "Sales Executive", "Accountant", "Staff"]
STAFF_STATUSES = ["Active", "Inactive"]

# ---------------------------------------------------------------------------
# Role-based sidebar/module access.
#
# "Admin" is the tenant's own admin (the account that signed up — i.e. the
# real-estate agency's owner/administrator, referred to as "Tenant Admin" in
# the SaaS documentation; the stored role value stays "Admin" so nothing
# breaks for existing accounts). Staff login accounts created from the Staff
# module get one of the other roles and only see the menu items listed for
# that role. "license", "logout" are always reachable for everyone so nobody
# gets permanently locked out.
#
# "Super Admin" is a separate, platform-level role (SN Softech Solutions
# only) that manages the SaaS platform itself — the list of tenants and
# their subscription status — and never sees any single tenant's business
# data. It is not selectable from the Staff module; see auth.py for how a
# Super Admin account is created.
# ---------------------------------------------------------------------------
ROLE_MENU_ACCESS = {
    "Super Admin": ["super_admin", "logout"],
    "Admin": None,  # None = full access, every menu item (this tenant's data only)
    "Manager": [
        "dashboard", "properties", "customers", "leads", "site_visits", "deals",
        "payments", "expenses", "staff", "reports", "kpi", "followups",
        "license", "logout",
    ],
    "Sales Executive": [
        "dashboard", "properties", "customers", "leads", "site_visits", "deals",
        "followups", "license", "logout",
    ],
    "Accountant": [
        "dashboard", "payments", "expenses", "reports", "license", "logout",
    ],
    "Staff": [
        "dashboard", "site_visits", "followups", "license", "logout",
    ],
}
# Backward compatibility: "Agent" was the role name used before this update
# introduced "Sales Executive" — keep it working identically for any
# existing staff logins created under the old name.
ROLE_MENU_ACCESS["Agent"] = ROLE_MENU_ACCESS["Sales Executive"]

CURRENCIES = {"INR (₹)": "₹", "USD ($)": "$", "GBP (£)": "£", "EUR (€)": "€"}
DATE_FORMATS = ["DD-MM-YYYY", "MM-DD-YYYY", "YYYY-MM-DD"]
THEMES = ["Light Professional", "Deep Blue", "Emerald"]

# ---------------------------------------------------------------------------
# Sidebar menu (icon, label, module key)
# ---------------------------------------------------------------------------
MENU_ITEMS = [
    ("🏠", "Dashboard", "dashboard", "#4F46E5"),
    ("🏢", "Property Management", "properties", "#0EA5E9"),
    ("👥", "Customers", "customers", "#10B981"),
    ("🎯", "Leads / CRM", "leads", "#F59E0B"),
    ("📅", "Site Visits", "site_visits", "#EF4444"),
    ("🤝", "Deals / Sales", "deals", "#8B5CF6"),
    ("💰", "Payments", "payments", "#14B8A6"),
    ("💸", "Expenses", "expenses", "#F97316"),
    ("👨‍💼", "Agents / Staff", "staff", "#EC4899"),
    ("📊", "Reports", "reports", "#6366F1"),
    ("📈", "KPI Analytics", "kpi", "#0891B2"),
    ("🔔", "Follow-ups / Reminders", "followups", "#D97706"),
    ("⚙️", "Settings", "settings", "#64748B"),
    ("🔐", "License", "license", "#7C3AED"),
    ("🛡️", "Super Admin", "super_admin", "#0F172A"),
    ("🚪", "Logout", "logout", "#DC2626"),
]
