"""
demo_data.py
Generates realistic sample data for a given user, ONLY when explicitly
requested via the "Load Demo Data" button in Settings. Never runs
automatically on a fresh production database.
"""

import random
import datetime

from database import run_query, log_activity

CITIES = [("Mumbai", "Andheri West"), ("Pune", "Baner"), ("Bengaluru", "Whitefield"),
          ("Delhi", "Dwarka"), ("Hyderabad", "Gachibowli"), ("Ahmedabad", "Satellite")]

FIRST_NAMES = ["Rahul", "Priya", "Amit", "Sneha", "Vikram", "Anjali", "Rohan", "Neha", "Karan", "Divya",
               "Arjun", "Pooja", "Sanjay", "Kavita", "Manish", "Ritu"]
LAST_NAMES = ["Sharma", "Verma", "Patel", "Reddy", "Iyer", "Gupta", "Nair", "Singh", "Mehta", "Joshi"]

PROPERTY_TYPES = ["Residential", "Commercial", "Plot/Land", "Apartment", "Villa", "Office", "Shop", "Warehouse"]
LISTING_TYPES = ["Sale", "Rent"]
PROP_STATUSES = ["Available", "Available", "Under Negotiation", "Sold", "Rented", "Hold"]
FURNISHED = ["Unfurnished", "Semi-Furnished", "Fully-Furnished"]
FACINGS = ["North", "South", "East", "West"]

LEAD_STATUSES = ["New", "Contacted", "Follow-up", "Site Visit", "Negotiation", "Converted", "Lost"]
LEAD_SOURCES = ["Website", "Referral", "Walk-in", "Phone Call", "Social Media", "Advertisement"]

DEAL_STATUSES = ["Negotiation", "Booked", "Completed"]
PAYMENT_MODES = ["Cash", "UPI", "Bank Transfer", "Cheque"]
EXPENSE_CATEGORIES = ["Office Rent", "Electricity", "Marketing", "Salary", "Travel", "Maintenance", "Advertisement"]
STAFF_ROLES = ["Manager", "Agent", "Agent", "Staff"]


def _name():
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"


def _mobile():
    return f"9{random.randint(100000000, 999999999)}"


def _rand_date(days_back=180):
    return (datetime.date.today() - datetime.timedelta(days=random.randint(0, days_back))).isoformat()


def load_demo_data(tenant_id):
    """Populates a realistic demo dataset for the given user. Idempotent-ish:
    running twice will simply add another batch of demo records."""

    # ---- Staff ----
    staff_ids = []
    for i in range(5):
        name = _name()
        sid = run_query(
            """INSERT INTO staff (tenant_id, name, mobile, email, role, joining_date, salary, commission_percent, status)
               VALUES (?,?,?,?,?,?,?,?, 'Active')""",
            (tenant_id, name, _mobile(), f"{name.split()[0].lower()}@example.com", random.choice(STAFF_ROLES),
             _rand_date(400), random.choice([25000, 30000, 35000, 40000]), random.choice([1, 2, 2.5, 3])),
        )
        staff_ids.append((sid, name))

    agent_names = [n for _, n in staff_ids] or ["Demo Agent"]

    # ---- Properties ----
    property_ids = []
    for i in range(25):
        city, locality = random.choice(CITIES)
        listing_type = random.choice(LISTING_TYPES)
        status = random.choice(PROP_STATUSES)
        price = random.choice([2500000, 4500000, 6000000, 8500000, 12000000, 18000000])
        rent = random.choice([15000, 25000, 35000, 50000, 75000])
        pid = run_query(
            """INSERT INTO properties (tenant_id, property_name, property_type, listing_type, owner_name, owner_mobile,
                address, city, locality, state, pincode, carpet_area, builtup_area, plot_area, bedrooms, bathrooms,
                floor, total_floors, furnished_status, facing, parking, price, rent_amount, security_deposit,
                status, description, image_path, date_added)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (tenant_id, f"{random.choice(['Sunrise','Green Valley','Skyline','Palm','Silver','Golden'])} {random.choice(['Residency','Heights','Enclave','Towers','Villa'])} #{i+1}",
             random.choice(PROPERTY_TYPES), listing_type, _name(), _mobile(), f"{random.randint(1,999)}, Main Road", city, locality,
             city, f"{random.randint(100000,999999)}", random.randint(500, 3000), random.randint(600, 3500), random.randint(0, 5000),
             random.randint(1, 5), random.randint(1, 4), str(random.randint(1, 20)), str(random.randint(1, 25)),
             random.choice(FURNISHED), random.choice(FACINGS), f"{random.randint(0,3)} Car", price, rent,
             rent * 2, status, "Spacious property in a prime location with excellent connectivity.", "", _rand_date(300)),
        )
        property_ids.append((pid, listing_type, status))

    # ---- Customers ----
    customer_ids = []
    for i in range(20):
        name = _name()
        cid = run_query(
            """INSERT INTO customers (tenant_id, name, mobile, whatsapp, email, address, requirement, preferred_location,
                budget, property_type_required, buy_or_rent, source, assigned_agent, notes, date_added)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (tenant_id, name, _mobile(), _mobile(), f"{name.split()[0].lower()}{i}@example.com",
             f"{random.randint(1,999)} Park Street", "2-3 BHK apartment", random.choice(CITIES)[1],
             random.choice([3000000, 5000000, 7000000, 9000000]), random.choice(PROPERTY_TYPES),
             random.choice(["Buying", "Renting"]), random.choice(LEAD_SOURCES), random.choice(agent_names),
             "Prefers ready-to-move properties.", _rand_date(200)),
        )
        customer_ids.append(cid)

    # ---- Leads ----
    for i in range(30):
        name = _name()
        followup = (datetime.date.today() + datetime.timedelta(days=random.randint(-5, 10))).isoformat()
        run_query(
            """INSERT INTO leads (tenant_id, lead_name, mobile, email, requirement, budget, preferred_location,
                property_type, source, assigned_agent, status, next_followup_date, notes, date_added)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (tenant_id, name, _mobile(), f"{name.split()[0].lower()}{i}@example.com", "Looking for investment property",
             random.choice([2000000, 4000000, 6000000, 10000000]), random.choice(CITIES)[1],
             random.choice(PROPERTY_TYPES), random.choice(LEAD_SOURCES), random.choice(agent_names),
             random.choice(LEAD_STATUSES), followup, "Interested, needs more details.", _rand_date(150)),
        )

    # ---- Site Visits ----
    for i in range(15):
        cid = random.choice(customer_ids)
        pid = random.choice(property_ids)[0]
        run_query(
            """INSERT INTO site_visits (tenant_id, customer_id, property_id, visit_date, visit_time, assigned_agent,
                status, feedback, remarks) VALUES (?,?,?,?,?,?,?,?,?)""",
            (tenant_id, cid, pid, (datetime.date.today() + datetime.timedelta(days=random.randint(-10, 5))).isoformat(),
             f"{random.randint(10,17)}:00", random.choice(agent_names), random.choice(["Scheduled", "Completed", "Cancelled"]),
             random.choice(["Liked the property", "Wants a bigger space", "Positive response", ""]), ""),
        )

    # ---- Deals + Payments ----
    for i in range(12):
        cid = random.choice(customer_ids)
        pid, listing_type, _ = random.choice(property_ids)
        property_value = random.choice([2500000, 4500000, 6000000, 8500000])
        discount = random.choice([0, 50000, 100000])
        final_amount = property_value - discount
        booking = random.choice([0, 100000, 300000, final_amount])
        status = random.choice(DEAL_STATUSES)
        payment_status = "Paid" if booking >= final_amount and final_amount > 0 else ("Partial" if booking > 0 else "Pending")
        deal_id = run_query(
            """INSERT INTO deals (tenant_id, customer_id, property_id, agent, deal_date, property_value, discount,
                final_amount, booking_amount, commission, payment_status, deal_status, remarks)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (tenant_id, cid, pid, random.choice(agent_names), _rand_date(120), property_value, discount, final_amount,
             booking, round(final_amount * 0.01, 2), payment_status, status, "Standard deal terms."),
        )
        if booking > 0:
            run_query(
                """INSERT INTO payments (tenant_id, deal_id, customer_id, property_id, payment_date, amount,
                    payment_mode, transaction_number, remarks) VALUES (?,?,?,?,?,?,?,?,?)""",
                (tenant_id, deal_id, cid, pid, _rand_date(100), booking, random.choice(PAYMENT_MODES),
                 f"TXN{random.randint(100000,999999)}", "Booking payment"),
            )
        if status == "Completed":
            new_status = "Sold" if listing_type == "Sale" else "Rented"
            run_query("UPDATE properties SET status = ? WHERE id = ?", (new_status, pid))

    # ---- Expenses ----
    for i in range(20):
        run_query(
            """INSERT INTO expenses (tenant_id, expense_date, category, description, amount, payment_mode, paid_by, remarks)
               VALUES (?,?,?,?,?,?,?,?)""",
            (tenant_id, _rand_date(150), random.choice(EXPENSE_CATEGORIES), "Routine business expense",
             random.choice([1500, 3000, 5000, 8000, 12000]), random.choice(PAYMENT_MODES), random.choice(agent_names), ""),
        )

    log_activity(tenant_id, "Load Demo Data", "Demo dataset generated.")
    return True
