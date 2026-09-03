# SN Real Estate Management System — Multi-Tenant SaaS Edition

This is the **online, multi-tenant** edition of the same SN Real Estate
Management System: multiple agencies/companies (tenants) share one deployed
app, each with completely isolated data, backed by **PostgreSQL**, deployed
via **GitHub + Streamlit Cloud**.

The original single-computer desktop edition (SQLite, `run.bat`) still works
unmodified — see `README.md`. Both editions share the exact same codebase;
which one runs is decided automatically by whether a PostgreSQL connection
string is configured (see Step 3 below). No code changes are needed to
switch between them.

---

## 1. Architecture at a glance

- **Multi-tenant model**: every business is a row in `tenants`. Every login
  (`users`) belongs to exactly one tenant via `users.tenant_id`. Every
  business table (properties, customers, leads, deals, payments, expenses,
  staff, followups) is scoped by `tenant_id`, and every query in every
  module filters by it — resolved from the authenticated session only,
  never from a URL parameter or form field a browser could tamper with.
- **No free trial**: a new signup is "Unlicensed" until a Monthly/Yearly
  license key is activated.
- **Demo account**: a protected, pre-seeded tenant with sample data anyone
  can log into (`demo` / `Demo@12345`) — cannot change its password, create
  staff logins, or edit its own configuration.
- **Super Admin**: a platform-level account (not tied to any tenant) that
  can see the list of tenants and their subscription status, and
  suspend/reactivate them — but never sees any tenant's business data.
- **Dual backend**: `db_config.py` auto-detects PostgreSQL (via Streamlit
  Secrets or `DATABASE_URL`) vs SQLite (offline desktop fallback).
  `database.py` translates the same `?`-style SQL to whichever backend is
  active, so all ~15 feature modules are backend-agnostic.

## 2. Push to GitHub

```bash
cd sn_realestate_saas
git init
git add .
git commit -m "Multi-tenant SaaS edition"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

`.gitignore` already excludes `.streamlit/secrets.toml`, `*.db`, `__pycache__/`,
and anything else sensitive — verify nothing secret is staged before your
first commit with `git status`.

## 3. Set up a PostgreSQL database

Any managed PostgreSQL provider works (Neon, Supabase, Render, Railway,
ElephantSQL, AWS RDS, etc.). You just need a connection string in this
format:

```
postgresql+psycopg2://USERNAME:PASSWORD@HOST:PORT/DATABASE_NAME
```

Free-tier options (Neon, Supabase) are enough to start. Create the database,
copy its connection string — you do not need to manually create any tables;
the app creates its own schema and seeds the demo account + Super Admin on
first startup (`database.py: init_db()`).

## 4. Deploy on Streamlit Cloud

1. Go to https://share.streamlit.io and sign in with GitHub.
2. Click "New app", pick your repository, branch `main`, and set the main
   file path to `app.py`.
3. Before (or right after) deploying, open **Settings → Secrets** on the
   app and paste:

   ```toml
   [database]
   url = "postgresql+psycopg2://USERNAME:PASSWORD@HOST:5432/DATABASE_NAME"

   [super_admin]
   username = "your-super-admin-username"
   password = "a-strong-unique-password"
   ```

   (See `.streamlit/secrets.toml.example` for the full template.)
4. Click "Deploy". Streamlit Cloud installs `requirements.txt`, reads your
   secrets, and starts `app.py`. On first boot, `init_db()` creates every
   table, seeds the license key pool, the demo tenant, and the Super Admin
   account automatically.
5. Visit your app's URL — you should see the Sign In / Sign Up screen.

**Do not skip setting the `[database]` secret** — without it, the app
silently falls back to a local SQLite file, which does NOT persist between
Streamlit Cloud restarts/redeploys and is NOT shared across multiple app
instances. PostgreSQL is required for the SaaS edition to actually work as
a persistent, multi-tenant service.

## 5. First login after deployment

- **Try the demo**: username `demo`, password `Demo@12345` — pre-loaded
  with realistic sample data, safe to click around.
- **Sign up a real tenant**: use the Sign Up tab, then activate a license
  key from `license_keys_seed.py` (50 Monthly + 50 Yearly keys are
  pre-loaded; issue them to real customers as you sell subscriptions —
  see that file's docstring for how to add more).
- **Super Admin**: sign in with the username/password you set in Secrets
  (`[super_admin]`) to see the tenant list and subscription overview.

## 6. Rotating the Super Admin password

The Super Admin account is seeded once, on first startup, using whatever
`[super_admin]` secret is present at that time (or the `config.py` defaults
if none is set — **change these immediately**, they are not meant for
production). To change the password afterward, update it directly in the
database (there's no in-app "change Super Admin password" screen in this
version):

```sql
-- Generate a new password hash with Python first:
-- python3 -c "import auth; print(auth._hash_password('YourNewPassword'))"
UPDATE users SET password_hash = '<paste hash here>' WHERE username = 'superadmin';
```

## 7. Backups

- **SQLite/offline edition**: use Settings → Application → Backup Database
  in-app (unchanged from before).
- **PostgreSQL/SaaS edition**: the in-app backup button is disabled (there's
  no single local file to copy). Use your PostgreSQL provider's own
  backup/snapshot/export tooling — most managed providers (Neon, Supabase,
  RDS) include automatic daily backups and a manual "export" option.

## 8. What's shared vs. what's separate between editions

| | Offline Desktop | Online SaaS |
|---|---|---|
| Database | SQLite (local file) | PostgreSQL (cloud) |
| Tenants | 1 per install (self-contained) | Many, fully isolated |
| Demo account | Not seeded | Seeded automatically |
| Super Admin | Not applicable | Seeded automatically |
| Backup | In-app button | Your PostgreSQL provider's tools |
| Code | **Same files, same repo** | **Same files, same repo** |

## 9. Known limitations (see the full report for details)

- File/image uploads (property photos, documents) are still written to the
  app server's local disk (`data/images`, `data/documents`), which is
  **not persistent** on Streamlit Cloud (the filesystem resets on redeploy
  and isn't shared across multiple app instances if you ever scale out).
  For production use with real property photos, wire in a cloud storage
  provider (S3, Cloudinary, etc.) — the upload code is centralized enough
  in each module to swap out, but this swap itself hasn't been done.
- Fine-grained per-staff-member audit trail: `activity_logs` now records
  both `tenant_id` and `user_id` (the real actor) at the points that matter
  most (signup, login, staff creation/revocation, license activation), but
  not yet on every single CRUD action across every module.
- Real payment gateway integration (Razorpay Payment Links) requires your
  own merchant account and API keys — see Settings → Payment Gateway.
- No automated database migrations tool (e.g. Alembic) — schema changes are
  handled by additive, idempotent `ALTER TABLE ... IF NOT EXISTS`-style
  checks in `database.py`, which is adequate for this app's schema size but
  would benefit from a real migration tool if the schema grows much further.
