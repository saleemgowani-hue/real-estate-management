"""
modules/properties.py
Property Management: add/search/edit/delete properties, image + document
attachments, Excel/PDF export.
"""

import os
import uuid

import streamlit as st

from config import (
    PROPERTY_TYPES, LISTING_TYPES, PROPERTY_STATUSES, FURNISHED_STATUSES,
    FACING_OPTIONS, IMAGES_DIR, DOCS_DIR,
)
from database import run_query, run_df, log_activity
from utils import today_str, fmt_date, fmt_currency, safe_float, safe_int, is_blank, dataframe_to_excel_bytes, dataframe_to_pdf_bytes
from style import badge_html


def render(tenant_id, currency_symbol, date_format):
    st.markdown(
        '<div class="sn-section-title">🏢 Property Management</div>'
        '<div class="sn-section-sub">Add, search, and manage your property listings.</div>',
        unsafe_allow_html=True,
    )

    tab_add, tab_manage = st.tabs(["➕ Add Property", "📋 Manage Properties"])

    with tab_add:
        _render_add_form(tenant_id)

    with tab_manage:
        _render_manage(tenant_id, currency_symbol, date_format)


def _render_add_form(tenant_id):
    st.markdown('<div class="sn-card">', unsafe_allow_html=True)
    with st.form("add_property_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            property_name = st.text_input("Property Name *")
            property_type = st.selectbox("Property Type", PROPERTY_TYPES)
            listing_type = st.selectbox("Listing Type", LISTING_TYPES)
            status = st.selectbox("Status", PROPERTY_STATUSES)
        with c2:
            owner_name = st.text_input("Owner Name")
            owner_mobile = st.text_input("Owner Mobile")
            city = st.text_input("City")
            locality = st.text_input("Locality")
        with c3:
            state = st.text_input("State")
            pincode = st.text_input("Pincode")
            address = st.text_area("Address", height=68)

        st.markdown("###### Area & Layout")
        c4, c5, c6, c7 = st.columns(4)
        with c4:
            carpet_area = st.number_input("Carpet Area (sqft)", min_value=0.0, step=1.0)
            bedrooms = st.number_input("Bedrooms", min_value=0, step=1)
        with c5:
            builtup_area = st.number_input("Builtup Area (sqft)", min_value=0.0, step=1.0)
            bathrooms = st.number_input("Bathrooms", min_value=0, step=1)
        with c6:
            plot_area = st.number_input("Plot Area (sqft)", min_value=0.0, step=1.0)
            floor = st.text_input("Floor")
        with c7:
            total_floors = st.text_input("Total Floors")
            parking = st.text_input("Parking")

        c8, c9 = st.columns(2)
        with c8:
            furnished_status = st.selectbox("Furnished Status", FURNISHED_STATUSES)
        with c9:
            facing = st.selectbox("Facing", FACING_OPTIONS)

        st.markdown("###### Pricing")
        c10, c11, c12 = st.columns(3)
        with c10:
            price = st.number_input("Sale Price", min_value=0.0, step=1000.0)
        with c11:
            rent_amount = st.number_input("Rent Amount", min_value=0.0, step=500.0)
        with c12:
            security_deposit = st.number_input("Security Deposit", min_value=0.0, step=500.0)

        description = st.text_area("Description")
        image_file = st.file_uploader("Property Image", type=["png", "jpg", "jpeg", "webp"])
        doc_files = st.file_uploader("Documents", accept_multiple_files=True)

        submitted = st.form_submit_button("Save Property", type="primary", use_container_width=True)

    if submitted:
        if is_blank(property_name):
            st.error("Property Name is required.")
        else:
            image_path = ""
            if image_file is not None:
                fname = f"{uuid.uuid4().hex}_{image_file.name}"
                with open(os.path.join(IMAGES_DIR, fname), "wb") as f:
                    f.write(image_file.getbuffer())
                image_path = fname

            pid = run_query(
                """INSERT INTO properties (tenant_id, property_name, property_type, listing_type, owner_name,
                    owner_mobile, address, city, locality, state, pincode, carpet_area, builtup_area, plot_area,
                    bedrooms, bathrooms, floor, total_floors, furnished_status, facing, parking, price, rent_amount,
                    security_deposit, status, description, image_path, date_added)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (tenant_id, property_name, property_type, listing_type, owner_name, owner_mobile, address, city,
                 locality, state, pincode, safe_float(carpet_area), safe_float(builtup_area), safe_float(plot_area),
                 safe_int(bedrooms), safe_int(bathrooms), floor, total_floors, furnished_status, facing, parking,
                 safe_float(price), safe_float(rent_amount), safe_float(security_deposit), status, description,
                 image_path, today_str()),
            )

            if doc_files:
                for doc in doc_files:
                    dfname = f"{uuid.uuid4().hex}_{doc.name}"
                    with open(os.path.join(DOCS_DIR, dfname), "wb") as f:
                        f.write(doc.getbuffer())
                    run_query(
                        "INSERT INTO property_documents (property_id, doc_name, doc_path) VALUES (?,?,?)",
                        (pid, doc.name, dfname),
                    )

            log_activity(tenant_id, "Property Added", f"Added property '{property_name}'")
            st.success("Property saved successfully.")
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)


def _render_manage(tenant_id, currency_symbol, date_format):
    st.markdown('<div class="sn-card">', unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    with c1:
        search = st.text_input("🔍 Search by name / city / locality / owner")
    with c2:
        f_type = st.selectbox("Property Type", ["All"] + PROPERTY_TYPES)
    with c3:
        f_listing = st.selectbox("Listing Type", ["All"] + LISTING_TYPES)
    with c4:
        f_status = st.selectbox("Status", ["All"] + PROPERTY_STATUSES)

    sql = "SELECT * FROM properties WHERE tenant_id = ?"
    params = [tenant_id]
    if search:
        sql += " AND (property_name LIKE ? OR city LIKE ? OR locality LIKE ? OR owner_name LIKE ?)"
        like = f"%{search}%"
        params += [like, like, like, like]
    if f_type != "All":
        sql += " AND property_type = ?"
        params.append(f_type)
    if f_listing != "All":
        sql += " AND listing_type = ?"
        params.append(f_listing)
    if f_status != "All":
        sql += " AND status = ?"
        params.append(f_status)
    sql += " ORDER BY id DESC"

    df = run_df(sql, tuple(params))

    if df.empty:
        st.info("No properties found.")
        st.markdown('</div>', unsafe_allow_html=True)
        return

    display_df = df.copy()
    display_df["price_display"] = display_df["price"].apply(lambda v: fmt_currency(v, currency_symbol))
    display_df["rent_display"] = display_df["rent_amount"].apply(lambda v: fmt_currency(v, currency_symbol))
    display_df["date_added_display"] = display_df["date_added"].apply(lambda v: fmt_date(v, date_format))

    st.dataframe(
        display_df[["id", "property_name", "property_type", "listing_type", "city", "locality",
                    "price_display", "rent_display", "status", "date_added_display"]].rename(columns={
            "property_name": "Name", "property_type": "Type", "listing_type": "Listing", "city": "City",
            "locality": "Locality", "price_display": "Price", "rent_display": "Rent", "status": "Status",
            "date_added_display": "Added",
        }),
        use_container_width=True, hide_index=True,
    )

    ce1, ce2 = st.columns(2)
    with ce1:
        st.download_button(
            "⬇️ Export Excel", dataframe_to_excel_bytes(display_df[[
                "property_name", "property_type", "listing_type", "city", "price", "rent_amount", "status"]],
                "Properties", "Property Listing"),
            file_name="properties.xlsx", use_container_width=True,
        )
    with ce2:
        st.download_button(
            "⬇️ Export PDF", dataframe_to_pdf_bytes(display_df[[
                "property_name", "property_type", "listing_type", "city", "price", "rent_amount", "status"]],
                "Property Listing"),
            file_name="properties.pdf", use_container_width=True,
        )

    st.markdown("---")
    options = {f"{row.id} — {row.property_name}": row.id for row in df.itertuples()}
    selected_label = st.selectbox("Select a property to view / edit / delete", list(options.keys()))
    selected_id = options[selected_label]
    _render_detail(tenant_id, selected_id, currency_symbol, date_format)

    st.markdown('</div>', unsafe_allow_html=True)


def _render_detail(tenant_id, property_id, currency_symbol, date_format):
    row = run_query("SELECT * FROM properties WHERE id = ? AND tenant_id = ?", (property_id, tenant_id), fetchone=True)
    if not row:
        st.warning("Property not found.")
        return

    st.markdown(f"#### {row['property_name']}  {badge_html(row['status'])}", unsafe_allow_html=True)

    if row.get("image_path"):
        img_path = os.path.join(IMAGES_DIR, row["image_path"])
        if os.path.exists(img_path):
            st.image(img_path, width=280)

    dc1, dc2, dc3 = st.columns(3)
    with dc1:
        st.write(f"**Type:** {row['property_type']} / {row['listing_type']}")
        st.write(f"**Owner:** {row['owner_name']} ({row['owner_mobile']})")
        st.write(f"**Location:** {row['locality']}, {row['city']}, {row['state']} - {row['pincode']}")
    with dc2:
        st.write(f"**Carpet Area:** {row['carpet_area']} sqft | **Builtup:** {row['builtup_area']} sqft")
        st.write(f"**Bedrooms/Bathrooms:** {row['bedrooms']} / {row['bathrooms']}")
        st.write(f"**Floor:** {row['floor']} of {row['total_floors']} | **Facing:** {row['facing']}")
    with dc3:
        st.write(f"**Price:** {fmt_currency(row['price'], currency_symbol)}")
        st.write(f"**Rent:** {fmt_currency(row['rent_amount'], currency_symbol)} | **Deposit:** {fmt_currency(row['security_deposit'], currency_symbol)}")
        st.write(f"**Added:** {fmt_date(row['date_added'], date_format)}")

    if row.get("description"):
        st.write(f"**Description:** {row['description']}")

    docs = run_df("SELECT * FROM property_documents WHERE property_id = ?", (property_id,))
    if not docs.empty:
        st.markdown("###### Documents")
        for d in docs.itertuples():
            dpath = os.path.join(DOCS_DIR, d.doc_path)
            if os.path.exists(dpath):
                with open(dpath, "rb") as f:
                    st.download_button(f"📄 {d.doc_name}", f.read(), file_name=d.doc_name, key=f"doc_{d.id}")

    st.markdown("---")
    tab_edit, tab_delete = st.tabs(["✏️ Edit", "🗑️ Delete"])

    with tab_edit:
        with st.form(f"edit_property_{property_id}"):
            e1, e2, e3 = st.columns(3)
            with e1:
                property_name = st.text_input("Property Name", value=row["property_name"])
                property_type = st.selectbox("Property Type", PROPERTY_TYPES, index=_safe_index(PROPERTY_TYPES, row["property_type"]))
                listing_type = st.selectbox("Listing Type", LISTING_TYPES, index=_safe_index(LISTING_TYPES, row["listing_type"]))
                status = st.selectbox("Status", PROPERTY_STATUSES, index=_safe_index(PROPERTY_STATUSES, row["status"]))
            with e2:
                owner_name = st.text_input("Owner Name", value=row["owner_name"] or "")
                owner_mobile = st.text_input("Owner Mobile", value=row["owner_mobile"] or "")
                city = st.text_input("City", value=row["city"] or "")
                locality = st.text_input("Locality", value=row["locality"] or "")
            with e3:
                price = st.number_input("Sale Price", min_value=0.0, step=1000.0, value=safe_float(row["price"]))
                rent_amount = st.number_input("Rent Amount", min_value=0.0, step=500.0, value=safe_float(row["rent_amount"]))
                security_deposit = st.number_input("Security Deposit", min_value=0.0, step=500.0, value=safe_float(row["security_deposit"]))
            description = st.text_area("Description", value=row["description"] or "")

            update_submitted = st.form_submit_button("Update Property", type="primary", use_container_width=True)

        if update_submitted:
            run_query(
                """UPDATE properties SET property_name=?, property_type=?, listing_type=?, owner_name=?,
                   owner_mobile=?, city=?, locality=?, price=?, rent_amount=?, security_deposit=?, status=?,
                   description=? WHERE id = ? AND tenant_id = ?""",
                (property_name, property_type, listing_type, owner_name, owner_mobile, city, locality,
                 safe_float(price), safe_float(rent_amount), safe_float(security_deposit), status, description,
                 property_id, tenant_id),
            )
            log_activity(tenant_id, "Property Updated", f"Updated property '{property_name}'")
            st.success("Property updated.")
            st.rerun()

    with tab_delete:
        st.warning(f"This will permanently delete '{row['property_name']}' and its documents.")
        confirm = st.checkbox("I confirm I want to delete this property", key=f"confirm_del_prop_{property_id}")
        if st.button("Delete Property", key=f"del_prop_{property_id}", disabled=not confirm):
            run_query("DELETE FROM property_documents WHERE property_id = ?", (property_id,))
            run_query("DELETE FROM properties WHERE id = ? AND tenant_id = ?", (property_id, tenant_id))
            log_activity(tenant_id, "Property Deleted", f"Deleted property '{row['property_name']}'")
            st.success("Property deleted.")
            st.rerun()


def _safe_index(options, value):
    try:
        return options.index(value)
    except (ValueError, TypeError):
        return 0
