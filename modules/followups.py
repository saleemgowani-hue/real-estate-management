"""
modules/followups.py
Consolidated follow-up / reminder center: due/overdue lead follow-ups
(leads.next_followup_date) plus ad-hoc reminders in the `followups` table
(linked to either a lead or a customer). Best-effort email reminders via
notifications.send_followup_reminder_email.
"""

import datetime
import streamlit as st

from database import run_query, run_df, log_activity
from utils import fmt_date
import notifications


def render(tenant_id, currency_symbol, date_format):
    st.markdown(
        '<div class="sn-section-title">🔔 Follow-ups / Reminders</div>'
        '<div class="sn-section-sub">Stay on top of due and overdue follow-ups across leads and customers.</div>',
        unsafe_allow_html=True,
    )
    tab_due, tab_add, tab_leads = st.tabs(["📋 Due Follow-ups", "➕ Add Follow-up", "🎯 Lead Reminders"])
    with tab_due:
        _render_due(tenant_id, date_format)
    with tab_add:
        _render_add_form(tenant_id)
    with tab_leads:
        _render_lead_reminders(tenant_id, date_format)


def _render_due(tenant_id, date_format):
    st.markdown('<div class="sn-card">', unsafe_allow_html=True)
    df = run_df(
        """SELECT f.*, l.lead_name, l.email AS lead_email, c.name AS customer_name, c.email AS customer_email
           FROM followups f
           LEFT JOIN leads l ON f.lead_id = l.id
           LEFT JOIN customers c ON f.customer_id = c.id
           WHERE f.tenant_id = ? AND f.is_done = 0
           ORDER BY f.followup_date ASC""",
        (tenant_id,),
    )
    if df.empty:
        st.info("No pending follow-ups. You're all caught up!")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    today = datetime.date.today()
    for row in df.itertuples():
        target_name = row.lead_name or row.customer_name or "Unknown"
        target_email = row.lead_email or row.customer_email or ""
        try:
            due_date = datetime.date.fromisoformat(str(row.followup_date)[:10])
        except ValueError:
            due_date = None
        overdue = due_date is not None and due_date < today

        with st.container():
            c1, c2, c3 = st.columns([3, 1, 1])
            with c1:
                label = f"**{target_name}** — {row.note or ''}"
                if overdue:
                    st.markdown(f":red[⚠️ OVERDUE — {fmt_date(row.followup_date, date_format)}]  \n{label}")
                else:
                    st.markdown(f"Due {fmt_date(row.followup_date, date_format)}  \n{label}")
            with c2:
                if st.button("✅ Mark Done", key=f"done_{row.id}"):
                    run_query("UPDATE followups SET is_done = 1 WHERE id = ? AND tenant_id = ?", (row.id, tenant_id))
                    log_activity(tenant_id, "Follow-up Completed", f"Follow-up #{row.id} marked done")
                    st.rerun()
            with c3:
                if target_email and st.button("✉️ Remind", key=f"remind_{row.id}"):
                    success, message = notifications.send_followup_reminder_email(tenant_id, target_email, target_name, row.note or "")
                    if success:
                        st.success("Reminder email sent.")
                    else:
                        st.info(message)
        st.markdown("---")

    st.markdown('</div>', unsafe_allow_html=True)


def _render_add_form(tenant_id):
    st.markdown('<div class="sn-card">', unsafe_allow_html=True)
    target_type = st.radio("Follow-up For", ["Lead", "Customer"], horizontal=True)

    if target_type == "Lead":
        options_df = run_df("SELECT id, lead_name FROM leads WHERE tenant_id = ? ORDER BY lead_name", (tenant_id,))
        label_col = "lead_name"
    else:
        options_df = run_df("SELECT id, name FROM customers WHERE tenant_id = ? ORDER BY name", (tenant_id,))
        label_col = "name"

    if options_df.empty:
        st.info(f"No {target_type.lower()}s found yet. Add one first.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    options = {f"{r.id} — {getattr(r, label_col)}": r.id for r in options_df.itertuples()}

    with st.form("add_followup_form", clear_on_submit=True):
        selected_label = st.selectbox(target_type, list(options.keys()))
        followup_date = st.date_input("Follow-up Date", value=datetime.date.today())
        note = st.text_area("Note")
        submitted = st.form_submit_button("Add Follow-up", type="primary", use_container_width=True)

    if submitted:
        target_id = options[selected_label]
        lead_id = target_id if target_type == "Lead" else None
        customer_id = target_id if target_type == "Customer" else None
        followup_id = run_query(
            "INSERT INTO followups (tenant_id, lead_id, customer_id, followup_date, note, is_done) VALUES (?,?,?,?,?,0)",
            (tenant_id, lead_id, customer_id, followup_date.isoformat(), note),
        )
        log_activity(tenant_id, "Follow-up Added", f"Follow-up #{followup_id} added")
        st.success("Follow-up added successfully.")
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


def _render_lead_reminders(tenant_id, date_format):
    st.markdown('<div class="sn-card">', unsafe_allow_html=True)
    st.caption("Leads with an upcoming or overdue next follow-up date, independent of the reminders above.")

    df = run_df(
        """SELECT id, lead_name, mobile, email, status, next_followup_date FROM leads
           WHERE tenant_id = ? AND next_followup_date IS NOT NULL AND next_followup_date != ''
             AND status NOT IN ('Converted', 'Lost')
           ORDER BY next_followup_date ASC""",
        (tenant_id,),
    )
    if df.empty:
        st.info("No leads with a pending follow-up date.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    today = datetime.date.today()
    display_df = df.copy()
    display_df["Follow-up Date"] = display_df["next_followup_date"].apply(lambda v: fmt_date(v, date_format))

    def _status_flag(v):
        try:
            d = datetime.date.fromisoformat(str(v)[:10])
        except ValueError:
            return ""
        if d < today:
            return "⚠️ Overdue"
        if d == today:
            return "🔔 Today"
        return "Upcoming"

    display_df["Urgency"] = display_df["next_followup_date"].apply(_status_flag)

    st.dataframe(
        display_df[["id", "lead_name", "mobile", "email", "status", "Follow-up Date", "Urgency"]].rename(columns={
            "id": "ID", "lead_name": "Lead", "mobile": "Mobile", "email": "Email", "status": "Status",
        }),
        use_container_width=True, hide_index=True,
    )

    st.caption("Update a lead's follow-up date or status from the Leads / CRM module.")
    st.markdown('</div>', unsafe_allow_html=True)
