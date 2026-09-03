# SN Real Estate Management System

A complete, production-ready Real Estate Management application for agencies, property dealers,
builders and brokers — built with Streamlit + SQLite.

**Powered by SN Softech Solutions**

---

## 0. Easiest way to get started (Windows)

1. Double-click **`run.bat`** — it installs everything automatically on first run and then
   starts the application in your browser. See **`Installation_Guide.docx`** for full,
   step-by-step instructions with screenshots-style walkthroughs.
2. Double-click **`Create Desktop Shortcut.bat`** once to add a Desktop icon so you can
   launch the app without opening this folder again.
3. Want to open it on your **phone or tablet** too? Use **`Start on Network (Phone-Tablet).bat`**
   instead of `run.bat` — it prints a network address you can open from any device on the
   same WiFi. See Section 4A of the Installation Guide.
4. For a full walkthrough of every feature (Sign Up, Sign In, Dashboard, Properties,
   Leads, Deals, Reports, etc.), open **`User_Manual.docx`**.

The rest of this README covers the manual / command-line installation path.

## 1. Installation (manual / macOS / Linux)

Requires Python 3.9+.

```bash
# 1. Unzip / copy the project folder, then move into it
cd sn_realestate

# 2. (Recommended) create a virtual environment
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

## 2. Run the application

```bash
streamlit run app.py
```

Open the URL Streamlit prints (usually `http://localhost:8501`).

The SQLite database is created automatically on first run at `data/sn_realestate.db` —
nothing to configure. Restarting the app never deletes existing data.

## 3. First-time login

There is no pre-seeded demo account — sign up from the **Sign Up** tab with your own
details. Every new account automatically receives a **3-day free trial** with full access
to every module.

To explore the app with realistic sample data, go to **Settings → (bottom of page) →
"Load Demo Data"** after logging in. This adds ~25 properties, 20 customers, 30 leads,
site visits, deals, payments, expenses and 5 staff records. It is opt-in only and never
runs automatically.

## 4. License testing

After the 3-day trial expires, the app blocks access to all modules except **License**
and **Settings**, and shows a "TRIAL EXPIRED" activation screen. To test license
activation without a real license server:

- Use the built-in demo key: `SNRE-DEMO-0000-0000`
- Or any key formatted like `SNRE-XXXX-XXXX-XXXX` (the offline demo validator accepts
  any correctly-formatted key — see `license.py`)

Activating sets the license to **Active** for **1 year** from the activation date.

To manually test trial expiry without waiting 3 days, you can backdate the trial start
in the database for your test account:

```python
from database import run_query
import datetime
run_query(
    "UPDATE licenses SET activation_date = ? WHERE user_id = ?",
    ((datetime.datetime.now() - datetime.timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S"), 1)
)
```

## 5. Connecting a real license server (production)

`license.py` isolates all license logic behind `validate_license_key()`. Replace its body
with an HTTPS call to your licensing API (passing the key + a device fingerprint) and
trust the API's response instead of the local `DEMO_VALID_KEYS` set. No other file needs
to change.

## 6. Project structure

```
sn_realestate/
├── app.py                 # Entry point: routing, sidebar, trial/license gating
├── config.py               # Single source of truth for paths, enums, trial/license length
├── database.py              # SQLite schema, connection helper, backup/restore
├── auth.py                  # Signup / login / password hashing (PBKDF2)
├── license.py               # Trial + license lifecycle (swap-in point for a real license API)
├── utils.py                  # Date/currency helpers, Excel export, PDF export
├── style.py                   # Custom CSS (professional multicolour UI)
├── demo_data.py                # Opt-in realistic sample-data generator
├── requirements.txt
├── modules/
│   ├── auth_pages.py        # Sign In / Sign Up / Forgot Password screens
│   ├── dashboard.py          # KPI cards + charts + alerts
│   ├── properties.py          # Property Management (CRUD, search, export)
│   ├── customers.py            # Customer Management
│   ├── leads.py                  # Leads / CRM pipeline
│   ├── site_visits.py             # Site Visit scheduling
│   ├── deals.py                     # Deal / Sales management (auto-updates property status)
│   ├── payments.py                    # Payment tracking against deals
│   ├── expenses.py                      # Expense tracking
│   ├── staff.py                           # Agent / Staff management
│   ├── reports.py                          # Reports Hub (14 report types, filters, export)
│   ├── kpi_analytics.py                     # Deep-dive KPI analytics
│   ├── followups.py                          # Consolidated follow-up/reminder center
│   ├── settings_page.py                       # Company profile, app prefs, backups, account
│   └── license_page.py                         # License activation screen
└── data/                     # SQLite DB + uploaded images/documents (auto-created)
```

## 7. Data export

Every major module (Properties, Customers, Leads, Site Visits, Deals, Payments, Expenses,
Staff, and every Report) supports **Excel export** (openpyxl) and **PDF export** (reportlab)
via download buttons.

## 8. Backup & restore

**Settings → Application → Backup Settings** lets you create a timestamped backup of the
live database and download it, or restore from a previously downloaded `.db` file
(a confirmation checkbox is required before any restore overwrites the current database).

## 9. Security notes

- Passwords are hashed with PBKDF2-HMAC-SHA256 (200,000 iterations) + a random salt per
  user — never stored in plain text.
- All database queries use parameterized SQL (no string-concatenated queries).
- Every user's data is scoped by `user_id` at the query level.
- License/trial state is centralized in `license.py`; the UI never contains its own
  copy of the expiry logic.
