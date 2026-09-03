"""
db_config.py
Single seam that decides which database backend is active:

- ONLINE / SaaS (Streamlit Cloud): PostgreSQL, configured via Streamlit
  Secrets (st.secrets["database"]["url"]) or the DATABASE_URL environment
  variable. This is the persistent, multi-tenant source of truth.
- OFFLINE / Desktop (run.bat on a single computer): local SQLite file,
  exactly as the original desktop edition worked. No code changes needed
  anywhere else in the app to run offline — just don't set DATABASE_URL /
  Streamlit secrets, and it behaves exactly like before.

Nothing else in the codebase should decide this — database.py reads
`BACKEND` and `DATABASE_URL` from here and nothing else needs to know
which backend is active.
"""

import os

from config import DB_PATH


def _get_database_url():
    """
    Resolution order:
    1. Streamlit Cloud Secrets: st.secrets["database"]["url"]
       (set in the Streamlit Cloud dashboard, never committed to GitHub)
    2. DATABASE_URL environment variable (useful for local Postgres testing,
       Docker, or any other host that isn't Streamlit Cloud)
    3. None -> falls back to local SQLite (offline desktop mode)
    """
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "database" in st.secrets and st.secrets["database"].get("url"):
            return st.secrets["database"]["url"]
    except Exception:
        pass  # st.secrets raises if no secrets.toml exists at all — that's fine, fall through

    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        return env_url

    return None


DATABASE_URL = _get_database_url()
BACKEND = "postgresql" if DATABASE_URL else "sqlite"

if BACKEND == "sqlite":
    # SQLAlchemy connection string for the same local file the desktop
    # edition has always used.
    DATABASE_URL = f"sqlite:///{DB_PATH}"
