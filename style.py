"""
style.py
Custom CSS injected once per page render so the app does not look like a
default Streamlit prototype.
"""

CUSTOM_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

    html, body, [class*="css"]  {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    .block-container {
        padding-top: 1.4rem;
        padding-bottom: 2rem;
        max-width: 1400px;
    }

    /* ---------- Top banner ---------- */
    .sn-topbar {
        background: linear-gradient(90deg, #4F46E5 0%, #7C3AED 60%, #0EA5E9 100%);
        padding: 18px 26px;
        border-radius: 16px;
        color: white;
        margin-bottom: 22px;
        box-shadow: 0 8px 24px rgba(79,70,229,0.25);
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
    }
    .sn-topbar h1 { font-size: 22px; margin: 0; font-weight: 800; letter-spacing: 0.3px; }
    .sn-topbar p { margin: 2px 0 0 0; opacity: 0.9; font-size: 13px; }

    /* ---------- License / subscription banners ---------- */
    .sn-banner {
        padding: 12px 20px;
        border-radius: 12px;
        font-weight: 600;
        margin-bottom: 18px;
        font-size: 14px;
        border-left: 6px solid;
    }
    .sn-banner-ok { background: #ECFDF5; color: #065F46; border-color: #10B981; }
    .sn-banner-warn { background: #FFFBEB; color: #92400E; border-color: #F59E0B; }
    .sn-banner-danger { background: #FEF2F2; color: #991B1B; border-color: #EF4444; }

    /* ---------- KPI Cards ---------- */
    .kpi-card {
        border-radius: 16px;
        padding: 18px 20px;
        color: white;
        box-shadow: 0 6px 18px rgba(0,0,0,0.10);
        margin-bottom: 14px;
        min-height: 108px;
        position: relative;
        overflow: hidden;
    }
    .kpi-card .kpi-label { font-size: 12.5px; opacity: 0.92; font-weight: 600; text-transform: uppercase; letter-spacing: 0.4px;}
    .kpi-card .kpi-value { font-size: 26px; font-weight: 800; margin-top: 6px; }
    .kpi-card .kpi-icon { position: absolute; right: 14px; top: 14px; font-size: 26px; opacity: 0.55; }

    /* ---------- Sidebar ---------- */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #111827 0%, #1F2937 100%);
    }
    section[data-testid="stSidebar"] .stButton button {
        width: 100%;
        text-align: left;
        border: none;
        padding: 11px 14px;
        border-radius: 10px;
        margin-bottom: 6px;
        font-weight: 600;
        font-size: 14.5px;
        transition: transform 0.12s ease, filter 0.12s ease;
        box-shadow: 0 2px 6px rgba(0,0,0,0.18);
    }
    section[data-testid="stSidebar"] .stButton button:hover {
        transform: translateX(3px) scale(1.01);
        filter: brightness(1.08);
    }
    section[data-testid="stSidebar"] .stButton button:focus {
        outline: none !important;
        box-shadow: 0 0 0 2px rgba(255,255,255,0.35) !important;
    }
    .sn-sidebar-brand {
        color: white; text-align:center; padding: 6px 0 16px 0;
        border-bottom: 1px solid rgba(255,255,255,0.12); margin-bottom: 14px;
    }
    .sn-sidebar-brand h2 { font-size: 17px; margin:0; font-weight: 800; }
    .sn-sidebar-brand span { font-size: 11px; color: #9CA3AF; }

    /* ---------- Generic cards / tables ---------- */
    .sn-card {
        background: white; border-radius: 14px; padding: 20px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.06); margin-bottom: 16px;
        border: 1px solid #F1F5F9;
    }
    .sn-section-title {
        font-size: 19px; font-weight: 800; color: #1E293B; margin-bottom: 4px;
    }
    .sn-section-sub { color: #64748B; font-size: 13px; margin-bottom: 14px; }

    div[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; }

    .stTextInput input, .stNumberInput input, .stTextArea textarea, .stDateInput input, .stSelectbox div[data-baseweb="select"] {
        border-radius: 10px !important;
    }

    .stButton>button {
        border-radius: 10px;
        font-weight: 600;
    }
    div.stButton > button[kind="primary"] {
        background: linear-gradient(90deg, #4F46E5, #7C3AED);
        border: none;
    }

    .sn-badge {
        display: inline-block; padding: 3px 10px; border-radius: 20px;
        font-size: 12px; font-weight: 700;
    }

    .sn-footer {
        text-align: center; color: #94A3B8; font-size: 12.5px;
        margin-top: 34px; padding-top: 14px; border-top: 1px solid #E2E8F0;
    }

    /* ==================================================================
       Responsive tuning — Tablet (≤1024px) and Phone (≤640px).
       Streamlit already stacks st.columns() vertically below ~640px on
       its own; these rules polish spacing, font sizes and touch-target
       sizing so the app is comfortable to use, not just technically usable,
       on a phone or tablet opened via "Start on Network".
       ================================================================== */
    @media (max-width: 1024px) {
        .block-container { padding-left: 1rem; padding-right: 1rem; }
        .kpi-card { min-height: 92px; padding: 14px 16px; }
        .kpi-card .kpi-value { font-size: 22px; }
    }

    @media (max-width: 640px) {
        .block-container { padding-top: 0.8rem; padding-left: 0.6rem; padding-right: 0.6rem; }

        .sn-topbar { padding: 14px 16px; border-radius: 12px; flex-direction: column; align-items: flex-start; }
        .sn-topbar h1 { font-size: 18px; }
        .sn-topbar p { font-size: 12px; }
        .sn-topbar div[style*="text-align:right"] { text-align: left !important; margin-top: 6px; }

        .sn-banner { padding: 10px 14px; font-size: 12.5px; }

        .sn-section-title { font-size: 17px; }
        .sn-section-sub { font-size: 12px; }

        .kpi-card { min-height: 78px; padding: 12px 14px; border-radius: 12px; }
        .kpi-card .kpi-label { font-size: 11px; }
        .kpi-card .kpi-value { font-size: 19px; margin-top: 3px; }
        .kpi-card .kpi-icon { font-size: 20px; right: 10px; top: 10px; }

        .sn-card { padding: 14px; border-radius: 12px; }

        /* Bigger touch targets on phones */
        .stButton>button, .stDownloadButton>button {
            min-height: 42px;
            font-size: 14px;
        }
        section[data-testid="stSidebar"] .stButton button {
            padding: 12px 14px;
            font-size: 14px;
        }

        div[data-testid="stDataFrame"] { font-size: 12.5px; }

        /* Plotly charts: let the container control height instead of a
           fixed desktop height so they don't get cropped on a phone */
        div[data-testid="stPlotlyChart"] > div { min-height: 260px !important; }
    }
</style>
"""

BADGE_COLORS = {
    "Available": ("#DCFCE7", "#166534"), "Sold": ("#FEE2E2", "#991B1B"),
    "Rented": ("#DBEAFE", "#1E40AF"), "Under Negotiation": ("#FEF3C7", "#92400E"),
    "Hold": ("#F3E8FF", "#6B21A8"), "Inactive": ("#F1F5F9", "#475569"),
    "New": ("#DBEAFE", "#1E40AF"), "Contacted": ("#E0E7FF", "#3730A3"),
    "Follow-up": ("#FEF3C7", "#92400E"), "Site Visit": ("#CFFAFE", "#155E75"),
    "Negotiation": ("#FEF3C7", "#92400E"), "Converted": ("#DCFCE7", "#166534"),
    "Lost": ("#FEE2E2", "#991B1B"), "Scheduled": ("#DBEAFE", "#1E40AF"),
    "Completed": ("#DCFCE7", "#166534"), "Cancelled": ("#FEE2E2", "#991B1B"),
    "Rescheduled": ("#FEF3C7", "#92400E"), "Booked": ("#E0E7FF", "#3730A3"),
    "Pending": ("#FEF3C7", "#92400E"), "Partial": ("#FEF9C3", "#854D0E"),
    "Paid": ("#DCFCE7", "#166534"), "Active": ("#DCFCE7", "#166534"),
    "Unlicensed": ("#E0E7FF", "#3730A3"), "Expired": ("#FEE2E2", "#991B1B"),
    "Invalid": ("#FEE2E2", "#991B1B"), "Suspended": ("#FEE2E2", "#991B1B"),
}


def badge_html(value):
    bg, fg = BADGE_COLORS.get(value, ("#F1F5F9", "#334155"))
    return f'<span class="sn-badge" style="background:{bg};color:{fg};">{value}</span>'
