"""
database.py
All direct database access lives here. UI code never opens a connection
or writes raw SQL against a driver directly.

DUAL BACKEND (see db_config.py):
  - SQLite  -> offline desktop edition (unchanged behaviour from before)
  - PostgreSQL -> online multi-tenant SaaS edition (Streamlit Cloud)

Every other file in this project calls run_query()/run_df() exactly as
before, with "?"-style positional placeholders — the translation to
SQLAlchemy's named-parameter style, and Postgres's "RETURNING id" for
getting a new row's id, both happen transparently in this file only.
This is what lets ~15 existing feature modules run unmodified against
either backend.

MULTI-TENANT MODEL:
  tenants          -- one row per customer/agency (the actual SaaS "tenant")
  users            -- login accounts; every user belongs to exactly one
                       tenant via users.tenant_id (see auth.py)
  company_settings -- ONE row per tenant (not a global singleton) so each
                       tenant has its own company profile / SMTP / payment
                       gateway configuration
  licenses         -- the tenant's subscription record (Monthly/Yearly),
                       keyed by tenant_id, shared by every user in that tenant
  All business tables (properties, customers, leads, site_visits, deals,
  payments, expenses, staff, followups) are scoped by tenant_id, and every
  query in every module already filters WHERE tenant_id = ? using the
  tenant_id resolved at login (see app.py) — never a client-supplied value.
"""

import re
import shutil
import datetime
import pandas as pd
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool, QueuePool

from config import DB_PATH, BACKUP_DIR
from db_config import DATABASE_URL, BACKEND

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------
if BACKEND == "postgresql":
    ENGINE = create_engine(
        DATABASE_URL,
        poolclass=QueuePool,
        pool_size=5,
        max_overflow=5,
        pool_pre_ping=True,   # survives Streamlit Cloud / cloud-DB idle disconnects
        pool_recycle=1800,
    )
else:
    ENGINE = create_engine(
        DATABASE_URL,
        poolclass=NullPool,
        connect_args={"check_same_thread": False, "timeout": 10},
    )

_INSERT_RE = re.compile(r"^\s*INSERT", re.IGNORECASE)


def _translate(sql, params):
    """
    Converts this project's "?"-style positional SQL (written once, used
    against both backends) into SQLAlchemy's named-parameter style, and —
    for PostgreSQL only — appends RETURNING id to INSERT statements so the
    new row's id can be read back the same way SQLite's lastrowid works.
    Returns (translated_sql, param_dict, is_insert).
    """
    is_insert = bool(_INSERT_RE.match(sql))
    if params:
        parts = sql.split("?")
        pieces = []
        param_dict = {}
        for i, part in enumerate(parts[:-1]):
            pname = f"p{i}"
            pieces.append(part)
            pieces.append(f":{pname}")
            param_dict[pname] = params[i]
        pieces.append(parts[-1])
        translated = "".join(pieces)
    else:
        translated = sql
        param_dict = {}

    if is_insert and BACKEND == "postgresql" and "RETURNING" not in translated.upper():
        translated = translated.rstrip().rstrip(";") + " RETURNING id"

    return translated, param_dict, is_insert


@contextmanager
def get_conn():
    """Yields a SQLAlchemy connection with an open transaction; commits on
    success, rolls back on any exception — same contract as the previous
    sqlite3-based version."""
    conn = ENGINE.connect()
    trans = conn.begin()
    try:
        yield conn
        trans.commit()
    except Exception:
        trans.rollback()
        raise
    finally:
        conn.close()


def run_query(sql, params=(), fetch=False, fetchone=False):
    """Execute a parameterized query. Returns rows if fetch requested,
    otherwise returns the new row's id for INSERT statements (mirrors the
    previous sqlite3 cur.lastrowid behaviour on both backends)."""
    translated, param_dict, is_insert = _translate(sql, params)
    with get_conn() as conn:
        result = conn.execute(text(translated), param_dict)
        if fetchone:
            row = result.mappings().first()
            return dict(row) if row else None
        if fetch:
            rows = result.mappings().all()
            return [dict(r) for r in rows]
        if is_insert:
            if BACKEND == "postgresql":
                try:
                    return result.scalar()
                except Exception:
                    return None
            return result.lastrowid
        return None


def run_df(sql, params=()):
    """Execute a SELECT and return a pandas DataFrame (safe on empty results)."""
    translated, param_dict, _ = _translate(sql, params)
    try:
        with ENGINE.connect() as conn:
            df = pd.read_sql_query(text(translated), conn, params=param_dict)
    except Exception:
        df = pd.DataFrame()
    return df


def executescript(conn, script):
    """Runs a multi-statement SQL script (schema DDL) one statement at a
    time — needed because, unlike sqlite3's executescript(), a plain
    SQLAlchemy/psycopg2 connection executes one statement per call."""
    for statement in script.split(";"):
        statement = statement.strip()
        if statement:
            conn.execute(text(statement))


def _insert_returning_id(conn, sql, params):
    """For internal migration/seed code that already holds an open `conn`
    (so it can't go through run_query()'s own transaction). Mirrors the
    same RETURNING-id shim run_query() uses, so raw INSERTs here also get
    a working id back on PostgreSQL (psycopg2 has no cursor.lastrowid) as
    well as SQLite."""
    if BACKEND == "postgresql" and "RETURNING" not in sql.upper():
        sql = sql.rstrip().rstrip(";") + " RETURNING id"
        return conn.execute(text(sql), params).scalar()
    return conn.execute(text(sql), params).lastrowid


# ---------------------------------------------------------------------------
# Schema — SQLite (offline desktop) and PostgreSQL (online SaaS) variants.
# Column names, defaults and relationships are kept identical between the
# two so every query written elsewhere in the app works unchanged.
# ---------------------------------------------------------------------------
SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_name TEXT NOT NULL,
    owner_name TEXT,
    mobile TEXT,
    email TEXT,
    is_demo INTEGER DEFAULT 0,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER,
    full_name TEXT NOT NULL,
    mobile TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'Admin',
    staff_id INTEGER,
    registration_date TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

CREATE TABLE IF NOT EXISTS company_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL UNIQUE,
    company_name TEXT DEFAULT 'SN Real Estate Management System',
    address TEXT DEFAULT '',
    mobile TEXT DEFAULT '',
    email TEXT DEFAULT '',
    website TEXT DEFAULT '',
    gst_number TEXT DEFAULT '',
    logo_path TEXT DEFAULT '',
    footer_text TEXT DEFAULT 'Powered by SN Softech Solutions',
    currency TEXT DEFAULT 'INR (₹)',
    date_format TEXT DEFAULT 'DD-MM-YYYY',
    theme TEXT DEFAULT 'Light Professional',
    smtp_enabled INTEGER DEFAULT 0,
    smtp_host TEXT DEFAULT '',
    smtp_port INTEGER DEFAULT 587,
    smtp_username TEXT DEFAULT '',
    smtp_password TEXT DEFAULT '',
    smtp_from_email TEXT DEFAULT '',
    smtp_from_name TEXT DEFAULT '',
    payment_gateway_enabled INTEGER DEFAULT 0,
    payment_gateway_provider TEXT DEFAULT 'Razorpay',
    payment_gateway_key_id TEXT DEFAULT '',
    payment_gateway_key_secret TEXT DEFAULT '',
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

CREATE TABLE IF NOT EXISTS licenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    license_key TEXT,
    plan_type TEXT DEFAULT 'Yearly',
    amount REAL,
    registered_mobile TEXT,
    registered_email TEXT,
    activation_date TEXT,
    expiry_date TEXT,
    status TEXT DEFAULT 'Unlicensed',
    payment_status TEXT DEFAULT 'Paid',
    transaction_id TEXT,
    created_at TEXT,
    updated_at TEXT,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

CREATE TABLE IF NOT EXISTS license_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    license_key TEXT NOT NULL UNIQUE,
    plan_type TEXT NOT NULL,
    status TEXT DEFAULT 'Unused',
    used_by_tenant_id INTEGER,
    used_date TEXT,
    FOREIGN KEY (used_by_tenant_id) REFERENCES tenants(id)
);

CREATE TABLE IF NOT EXISTS properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    property_name TEXT NOT NULL,
    property_type TEXT,
    listing_type TEXT,
    owner_name TEXT,
    owner_mobile TEXT,
    address TEXT,
    city TEXT,
    locality TEXT,
    state TEXT,
    pincode TEXT,
    carpet_area REAL,
    builtup_area REAL,
    plot_area REAL,
    bedrooms INTEGER,
    bathrooms INTEGER,
    floor TEXT,
    total_floors TEXT,
    furnished_status TEXT,
    facing TEXT,
    parking TEXT,
    price REAL,
    rent_amount REAL,
    security_deposit REAL,
    status TEXT DEFAULT 'Available',
    description TEXT,
    image_path TEXT,
    date_added TEXT,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

CREATE TABLE IF NOT EXISTS property_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_id INTEGER NOT NULL,
    doc_name TEXT,
    doc_path TEXT,
    FOREIGN KEY (property_id) REFERENCES properties(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    mobile TEXT,
    whatsapp TEXT,
    email TEXT,
    address TEXT,
    requirement TEXT,
    preferred_location TEXT,
    budget REAL,
    property_type_required TEXT,
    buy_or_rent TEXT,
    source TEXT,
    assigned_agent TEXT,
    notes TEXT,
    date_added TEXT,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    lead_name TEXT NOT NULL,
    mobile TEXT,
    email TEXT,
    requirement TEXT,
    budget REAL,
    preferred_location TEXT,
    property_type TEXT,
    source TEXT,
    assigned_agent TEXT,
    status TEXT DEFAULT 'New',
    next_followup_date TEXT,
    notes TEXT,
    date_added TEXT,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

CREATE TABLE IF NOT EXISTS site_visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    customer_id INTEGER,
    property_id INTEGER,
    visit_date TEXT,
    visit_time TEXT,
    assigned_agent TEXT,
    status TEXT DEFAULT 'Scheduled',
    feedback TEXT,
    remarks TEXT,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (property_id) REFERENCES properties(id)
);

CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    customer_id INTEGER,
    property_id INTEGER,
    agent TEXT,
    deal_date TEXT,
    property_value REAL,
    discount REAL DEFAULT 0,
    final_amount REAL,
    booking_amount REAL DEFAULT 0,
    commission REAL DEFAULT 0,
    payment_status TEXT DEFAULT 'Pending',
    deal_status TEXT DEFAULT 'Negotiation',
    remarks TEXT,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (property_id) REFERENCES properties(id)
);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    deal_id INTEGER,
    customer_id INTEGER,
    property_id INTEGER,
    payment_date TEXT,
    amount REAL,
    payment_mode TEXT,
    transaction_number TEXT,
    remarks TEXT,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (deal_id) REFERENCES deals(id),
    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (property_id) REFERENCES properties(id)
);

CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    expense_date TEXT,
    category TEXT,
    description TEXT,
    amount REAL,
    payment_mode TEXT,
    paid_by TEXT,
    remarks TEXT,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

CREATE TABLE IF NOT EXISTS staff (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    mobile TEXT,
    email TEXT,
    role TEXT DEFAULT 'Sales Executive',
    joining_date TEXT,
    salary REAL,
    commission_percent REAL,
    status TEXT DEFAULT 'Active',
    FOREIGN KEY (tenant_id) REFERENCES tenants(id)
);

CREATE TABLE IF NOT EXISTS followups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER NOT NULL,
    lead_id INTEGER,
    customer_id INTEGER,
    followup_date TEXT,
    note TEXT,
    is_done INTEGER DEFAULT 0,
    FOREIGN KEY (tenant_id) REFERENCES tenants(id),
    FOREIGN KEY (lead_id) REFERENCES leads(id),
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE IF NOT EXISTS activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id INTEGER,
    user_id INTEGER,
    action TEXT,
    details TEXT,
    timestamp TEXT
);
"""

# Index creation is kept SEPARATE from table creation and run only AFTER
# legacy migrations (see init_db()) — an upgrading desktop install adds its
# tenant_id column via ALTER TABLE during migration, so an index on that
# column can't be created until the column actually exists.
SQLITE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_properties_tenant ON properties(tenant_id);
CREATE INDEX IF NOT EXISTS idx_customers_tenant ON customers(tenant_id);
CREATE INDEX IF NOT EXISTS idx_leads_tenant ON leads(tenant_id);
CREATE INDEX IF NOT EXISTS idx_site_visits_tenant ON site_visits(tenant_id);
CREATE INDEX IF NOT EXISTS idx_deals_tenant ON deals(tenant_id);
CREATE INDEX IF NOT EXISTS idx_payments_tenant ON payments(tenant_id);
CREATE INDEX IF NOT EXISTS idx_expenses_tenant ON expenses(tenant_id);
CREATE INDEX IF NOT EXISTS idx_staff_tenant ON staff(tenant_id);
CREATE INDEX IF NOT EXISTS idx_followups_tenant ON followups(tenant_id);
CREATE INDEX IF NOT EXISTS idx_license_keys_status ON license_keys(status);
CREATE INDEX IF NOT EXISTS idx_activity_logs_tenant ON activity_logs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_leads_followup_date ON leads(next_followup_date);
CREATE INDEX IF NOT EXISTS idx_site_visits_date ON site_visits(visit_date);
"""

# PostgreSQL variant: same columns/defaults, SERIAL instead of
# AUTOINCREMENT, TIMESTAMP left as TEXT deliberately (unchanged business
# logic — every date is formatted/parsed as a string throughout the app
# on both backends, so this keeps behaviour identical rather than
# "improving" it into a type change that risks breaking existing code).
POSTGRES_SCHEMA = re.sub(
    r"INTEGER PRIMARY KEY AUTOINCREMENT",
    "SERIAL PRIMARY KEY",
    SQLITE_SCHEMA,
)
POSTGRES_INDEXES = SQLITE_INDEXES


def _indexes_for_backend():
    return POSTGRES_INDEXES if BACKEND == "postgresql" else SQLITE_INDEXES




def _schema_for_backend():
    return POSTGRES_SCHEMA if BACKEND == "postgresql" else SQLITE_SCHEMA


# ---------------------------------------------------------------------------
# Migration helpers
# ---------------------------------------------------------------------------
def _table_columns(conn, table):
    if BACKEND == "postgresql":
        rows = conn.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
            {"t": table},
        ).fetchall()
        return [r[0] for r in rows]
    else:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return [r[1] for r in rows]


def _table_exists(conn, table):
    if BACKEND == "postgresql":
        row = conn.execute(
            text("SELECT to_regclass(:t) IS NOT NULL AS exists_flag"), {"t": table}
        ).fetchone()
        return bool(row[0]) if row else False
    else:
        row = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"), {"t": table}
        ).fetchone()
        return row is not None


def _migrate_legacy_installation(conn):
    """
    Upgrades a pre-multi-tenant desktop database (which used a self-owned
    `owner_id` on `users` and a single global `company_settings` row) into
    the tenant-based schema, WITHOUT deleting any business data. Safe to
    call on every startup — every step is a no-op once already migrated.
    This path only matters for SQLite (an existing desktop install being
    upgraded); a brand-new PostgreSQL SaaS database never has this legacy
    shape, so nothing here runs for it.
    """
    if BACKEND == "postgresql":
        return
    if not _table_exists(conn, "users"):
        return  # brand-new database — nothing to migrate

    user_cols = _table_columns(conn, "users")
    if "tenant_id" in user_cols:
        return  # already migrated

    # This is an old desktop install: users.owner_id (self-referencing)
    # identified each tenant. Create one tenants row per distinct owner_id
    # group and point users.tenant_id at it.
    conn.execute(text("ALTER TABLE users ADD COLUMN tenant_id INTEGER"))
    has_owner_id = "owner_id" in user_cols
    if has_owner_id:
        owner_ids = [r[0] for r in conn.execute(
            text("SELECT DISTINCT owner_id FROM users WHERE owner_id IS NOT NULL")
        ).fetchall()]
        for owner_id in owner_ids:
            admin_row = conn.execute(
                text("SELECT full_name, mobile, email FROM users WHERE id = :id"), {"id": owner_id}
            ).fetchone()
            if not admin_row:
                continue
            new_tenant_id = conn.execute(
                text("INSERT INTO tenants (company_name, owner_name, mobile, email, created_at) "
                     "VALUES (:cn, :on, :mo, :em, :ca)"),
                {"cn": f"{admin_row[0]}'s Business", "on": admin_row[0], "mo": admin_row[1],
                 "em": admin_row[2], "ca": datetime.datetime.now().isoformat(timespec="seconds")},
            ).lastrowid
            conn.execute(
                text("UPDATE users SET tenant_id = :tid WHERE owner_id = :oid"),
                {"tid": new_tenant_id, "oid": owner_id},
            )
            # Re-point every business table's old user_id (which held the
            # owner_id value) at the new tenant_id.
            for table in ("properties", "customers", "leads", "site_visits", "deals",
                           "payments", "expenses", "staff", "followups"):
                if _table_exists(conn, table) and "user_id" in _table_columns(conn, table):
                    conn.execute(
                        text(f"UPDATE {table} SET user_id = :tid WHERE user_id = :oid"),
                        {"tid": new_tenant_id, "oid": owner_id},
                    )
            if _table_exists(conn, "licenses") and "user_id" in _table_columns(conn, "licenses"):
                conn.execute(
                    text("UPDATE licenses SET user_id = :tid WHERE user_id = :oid"),
                    {"tid": new_tenant_id, "oid": owner_id},
                )

    # Rename the now tenant-holding user_id column to tenant_id on every
    # business table (SQLite 3.25+ supports RENAME COLUMN).
    for table in ("properties", "customers", "leads", "site_visits", "deals",
                   "payments", "expenses", "staff", "followups", "licenses"):
        if _table_exists(conn, table) and "user_id" in _table_columns(conn, table) \
                and "tenant_id" not in _table_columns(conn, table):
            conn.execute(text(f"ALTER TABLE {table} RENAME COLUMN user_id TO tenant_id"))

    if _table_exists(conn, "license_keys") and "used_by_user_id" in _table_columns(conn, "license_keys"):
        conn.execute(text("ALTER TABLE license_keys RENAME COLUMN used_by_user_id TO used_by_tenant_id"))

    if _table_exists(conn, "activity_logs"):
        al_cols = _table_columns(conn, "activity_logs")
        if "tenant_id" not in al_cols:
            conn.execute(text("ALTER TABLE activity_logs ADD COLUMN tenant_id INTEGER"))
            conn.execute(text("UPDATE activity_logs SET tenant_id = user_id"))

    # company_settings: migrate the old single global row (id = 1) into a
    # proper tenant-scoped row for each tenant now known.
    if _table_exists(conn, "company_settings"):
        cs_cols = _table_columns(conn, "company_settings")
        if "tenant_id" not in cs_cols:
            old_settings = conn.execute(text("SELECT * FROM company_settings WHERE id = 1")).mappings().first()
            conn.execute(text("ALTER TABLE company_settings ADD COLUMN tenant_id INTEGER"))
            tenant_ids = [r[0] for r in conn.execute(text("SELECT id FROM tenants")).fetchall()]
            for tid in tenant_ids:
                cols_to_copy = {k: v for k, v in dict(old_settings or {}).items() if k not in ("id", "tenant_id")}
                col_names = ", ".join(list(cols_to_copy.keys()) + ["tenant_id"])
                placeholders = ", ".join([f":{k}" for k in cols_to_copy.keys()] + [":tenant_id"])
                params = {**cols_to_copy, "tenant_id": tid}
                conn.execute(text(f"INSERT INTO company_settings ({col_names}) VALUES ({placeholders})"), params)


def _migrate_additive_columns(conn):
    """Safe, additive migration for installs created before newer features
    (Monthly subscriptions, email, payment gateway, subscription pricing
    fields) existed. Never touches or deletes existing data."""
    lic_cols = _table_columns(conn, "licenses")
    additions = {
        "plan_type": "TEXT DEFAULT 'Yearly'", "amount": "REAL", "payment_status": "TEXT DEFAULT 'Paid'",
        "transaction_id": "TEXT", "created_at": "TEXT", "updated_at": "TEXT",
    }
    for col, coltype in additions.items():
        if col not in lic_cols:
            conn.execute(text(f"ALTER TABLE licenses ADD COLUMN {col} {coltype}"))

    settings_cols = _table_columns(conn, "company_settings")
    settings_additions = {
        "smtp_enabled": "INTEGER DEFAULT 0", "smtp_host": "TEXT DEFAULT ''",
        "smtp_port": "INTEGER DEFAULT 587", "smtp_username": "TEXT DEFAULT ''",
        "smtp_password": "TEXT DEFAULT ''", "smtp_from_email": "TEXT DEFAULT ''",
        "smtp_from_name": "TEXT DEFAULT ''", "payment_gateway_enabled": "INTEGER DEFAULT 0",
        "payment_gateway_provider": "TEXT DEFAULT 'Razorpay'", "payment_gateway_key_id": "TEXT DEFAULT ''",
        "payment_gateway_key_secret": "TEXT DEFAULT ''",
    }
    for col, coltype in settings_additions.items():
        if col not in settings_cols:
            conn.execute(text(f"ALTER TABLE company_settings ADD COLUMN {col} {coltype}"))

    tenant_cols = _table_columns(conn, "tenants") if _table_exists(conn, "tenants") else []
    if tenant_cols and "is_demo" not in tenant_cols:
        conn.execute(text("ALTER TABLE tenants ADD COLUMN is_demo INTEGER DEFAULT 0"))

    # Policy change: the free trial has been removed. Any account still
    # sitting on the old "Trial" status now requires a real license key,
    # exactly like a brand-new signup. This does not touch any business
    # data — only the license row's status.
    conn.execute(text("UPDATE licenses SET status = 'Unlicensed' WHERE status = 'Trial'"))


def init_db():
    """Create all tables if they do not already exist, run migrations, and
    seed license keys + demo tenant + super admin. Never drops data.
    Order matters: tables -> legacy/additive migrations (which may ADD
    columns like tenant_id to an old install) -> indexes (which may
    reference those columns) -> seed data."""
    new_demo_tenant_id = None
    with get_conn() as conn:
        executescript(conn, _schema_for_backend())
        _migrate_legacy_installation(conn)
        _migrate_additive_columns(conn)
        executescript(conn, _indexes_for_backend())
        _seed_license_keys(conn)
        new_demo_tenant_id = _seed_demo_tenant(conn)
        _seed_super_admin(conn)

    # Populated AFTER the schema/seed transaction above has committed —
    # load_demo_data() opens its own connection(s) via run_query(), which
    # would otherwise contend with the still-open transaction above
    # (especially on SQLite, where a second writer can't proceed until
    # the first commits).
    if new_demo_tenant_id:
        try:
            from demo_data import load_demo_data
            load_demo_data(new_demo_tenant_id)
        except Exception:
            pass  # demo data is a nice-to-have; never block startup on it


def _seed_license_keys(conn):
    """Load the pre-issued key pool from license_keys_seed.py. Only inserts
    keys that aren't already present, so it's safe to call on every startup
    and safe to append new keys to the seed file later without duplicating
    or resetting keys that have already been sold/used."""
    try:
        from license_keys_seed import LICENSE_KEY_SEED
    except ImportError:
        return
    existing = {r[0] for r in conn.execute(text("SELECT license_key FROM license_keys")).fetchall()}
    for key, plan_type in LICENSE_KEY_SEED:
        if key in existing:
            continue
        conn.execute(
            text("INSERT INTO license_keys (license_key, plan_type, status) VALUES (:k, :p, 'Unused')"),
            {"k": key, "p": plan_type},
        )


def _seed_demo_tenant(conn):
    """Creates the protected demo tenant + demo login exactly once. Safe to
    call on every startup — never duplicates. Returns the new tenant_id if
    one was just created (so the caller can populate sample data outside
    this transaction), or None if the demo tenant already existed."""
    from config import DEMO_USERNAME
    existing = conn.execute(text("SELECT id FROM users WHERE username = :u"), {"u": DEMO_USERNAME}).fetchone()
    if existing:
        return None  # already seeded, nothing to do

    now = datetime.datetime.now().isoformat(timespec="seconds")
    tenant_id = _insert_returning_id(
        conn,
        "INSERT INTO tenants (company_name, owner_name, mobile, email, is_demo, created_at) "
        "VALUES (:cn, :on, :mo, :em, 1, :ca)",
        {"cn": "SN Demo Realty (Sample Account)", "on": "Demo Admin", "mo": "9999999999",
         "em": "demo@snsoftech.example", "ca": now},
    )

    conn.execute(
        text("INSERT INTO company_settings (tenant_id, company_name, footer_text) "
             "VALUES (:tid, :cn, :ft)"),
        {"tid": tenant_id, "cn": "SN Demo Realty (Sample Account)", "ft": "Powered by SN Softech Solutions — DEMO DATA"},
    )

    import auth  # local import: auth imports database, avoid circular import at module load time
    password_hash = auth._hash_password("Demo@12345")
    conn.execute(
        text("INSERT INTO users (tenant_id, full_name, mobile, email, username, password_hash, role, registration_date) "
             "VALUES (:tid, :fn, :mo, :em, :un, :ph, 'Admin', :rd)"),
        {"tid": tenant_id, "fn": "Demo Admin", "mo": "9999999999", "em": "demo@snsoftech.example",
         "un": DEMO_USERNAME, "ph": password_hash, "rd": now},
    )

    # Demo tenant gets a permanent, always-Active Yearly subscription so
    # visitors never hit a license wall.
    far_future = (datetime.datetime.now() + datetime.timedelta(days=3650)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        text("INSERT INTO licenses (tenant_id, license_key, plan_type, activation_date, expiry_date, "
             "status, payment_status, created_at) "
             "VALUES (:tid, 'DEMO-PERMANENT', 'Yearly', :ad, :ed, 'Active', 'Paid', :ca)"),
        {"tid": tenant_id, "ad": now, "ed": far_future, "ca": now},
    )

    return tenant_id


def _seed_super_admin(conn):
    """Creates the platform-level Super Admin account exactly once — not
    tied to any tenant (tenant_id stays NULL). Picks up an override from
    Streamlit secrets ([super_admin] username/password) if present, else
    uses the config.py defaults (which you should change immediately after
    first deploying to a real environment)."""
    from config import SUPER_ADMIN_USERNAME, SUPER_ADMIN_DEFAULT_PASSWORD

    username = SUPER_ADMIN_USERNAME
    password = SUPER_ADMIN_DEFAULT_PASSWORD
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "super_admin" in st.secrets:
            username = st.secrets["super_admin"].get("username", username)
            password = st.secrets["super_admin"].get("password", password)
    except Exception:
        pass

    existing = conn.execute(text("SELECT id FROM users WHERE username = :u"), {"u": username}).fetchone()
    if existing:
        return

    import auth
    now = datetime.datetime.now().isoformat(timespec="seconds")
    conn.execute(
        text("INSERT INTO users (tenant_id, full_name, mobile, email, username, password_hash, role, registration_date) "
             "VALUES (NULL, 'Platform Super Admin', '0000000000', :em, :un, :ph, 'Super Admin', :rd)"),
        {"em": f"{username}@snsoftech.internal", "un": username, "ph": auth._hash_password(password), "rd": now},
    )


def log_activity(tenant_id, action, details="", actor_user_id=None):
    """Records an audit-log entry. `tenant_id` scopes the business; pass
    `actor_user_id` when the actual signed-in user's own id is known (e.g.
    from app.py) for precise per-user attribution — otherwise it falls back
    to tenant_id itself (the tenant's own admin), matching prior behaviour."""
    try:
        run_query(
            "INSERT INTO activity_logs (tenant_id, user_id, action, details, timestamp) VALUES (?, ?, ?, ?, ?)",
            (tenant_id, actor_user_id if actor_user_id is not None else tenant_id, action, details,
             datetime.datetime.now().isoformat(timespec="seconds")),
        )
    except Exception:
        pass  # activity logging must never break the app


# ---------------------------------------------------------------------------
# Backup / Restore (SQLite / offline desktop edition only — a PostgreSQL
# SaaS deployment should use your hosting provider's database backups,
# e.g. Streamlit Cloud's underlying Postgres provider's snapshot/export
# tooling, since there is no single local file to copy).
# ---------------------------------------------------------------------------
def backup_database():
    if BACKEND != "sqlite":
        raise RuntimeError(
            "Local file backup is only available in offline/desktop (SQLite) mode. "
            "In the online SaaS edition, use your PostgreSQL provider's backup/export tools."
        )
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = f"{BACKUP_DIR}/sn_realestate_backup_{ts}.db"
    shutil.copy2(DB_PATH, dest)
    return dest


def restore_database(uploaded_file_path):
    """Overwrites the live DB. Caller MUST confirm with the user first."""
    if BACKEND != "sqlite":
        raise RuntimeError(
            "Restoring from a local file is only available in offline/desktop (SQLite) mode."
        )
    shutil.copy2(uploaded_file_path, DB_PATH)
