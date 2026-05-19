import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from fpdf import FPDF

conn = sqlite3.connect('loans.db', check_same_thread=False)
c = conn.cursor()

# Schema
c.execute("PRAGMA table_info(loans)")
cols = [col[1] for col in c.fetchall()]
if 'frozen_balance' not in cols:
    c.execute("ALTER TABLE loans ADD COLUMN frozen_balance REAL DEFAULT 0")

c.execute('''CREATE TABLE IF NOT EXISTS loans (
             id INTEGER PRIMARY KEY, borrower_name TEXT, phone TEXT, amount REAL,
             interest_rate REAL, term_months INTEGER, total_repayment REAL,
             disbursement_date TEXT, due_date TEXT, amount_paid REAL DEFAULT 0,
             loan_officer TEXT, frozen INTEGER DEFAULT 0, frozen_balance REAL DEFAULT 0)''')

c.execute('''CREATE TABLE IF NOT EXISTS payments (
             id INTEGER PRIMARY KEY, loan_id INTEGER, amount REAL, payment_date TEXT)''')
conn.commit()

def calculate_penalty(due_date_str, balance, frozen):
    if frozen: return 0
    try:
        due = datetime.strptime(due_date_str, '%Y-%m-%d').date()
        today = datetime.now().date()
        grace_end = due + timedelta(days=10)
        if today <= grace_end or balance <= 0:
            return 0
        days_late = (today - grace_end).days
        return round(balance * 0.01 * days_late)
    except:
        return 0

# ====================== LOGIN ======================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.title("🔐 PROSPER MACRO SOLUTIONS LTD")
    st.subheader("Login")
    username = st.text_input("Username", key="login_user")
    password = st.text_input("Password", type="password", key="login_pass")
    if st.button("Login"):
        if username == "admin" and password == "123456":
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("Wrong credentials")
    st.stop()

# ====================== MAIN APP ======================
st.set_page_config(page_title="Prosper Macro", layout="wide")
st.title("PROSPER MACRO SOLUTIONS LTD")
st.subheader("Loan Management System")

tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Dashboard", "📝 New Loan", "📋 Loans Portfolio", "💰 Record Payment", "📜 History & Statement"])

with tab1:
    st.subheader("Business Dashboard")
    col1, col2, col3, col4 = st.columns(4)
    total_loans = pd.read_sql_query("SELECT COUNT(*) as count FROM loans", conn).iloc[0]['count']
    total_portfolio = pd.read_sql_query("SELECT COALESCE(SUM(total_repayment),0) as total FROM loans", conn).iloc[0]['total']
    total_collected = pd.read_sql_query("SELECT COALESCE(SUM(amount_paid),0) as collected FROM loans", conn).iloc[0]['collected']
    overdue = pd.read_sql_query("SELECT COUNT(*) as count FROM loans WHERE due_date < DATE('now') AND (total_repayment - COALESCE(amount_paid,0)) > 0 AND frozen = 0", conn).iloc[0]['count']
    
    col1.metric("Total Loans", total_loans)
    col2.metric("Total Portfolio", f"UGX {total_portfolio:,.0f}")
    col3.metric("Collected", f"UGX {total_collected:,.0f}")
    col4.metric("Overdue", overdue, delta="⚠️" if overdue > 0 else None)

with tab2:
    st.subheader("New Loan")
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("Borrower Name*", key="new_name")
        phone = st.text_input("Phone Number*", key="new_phone")
        amount = st.number_input("Loan Amount (UGX)", min_value=10000, value=100000, key="new_amount")
        officer = st.text_input("Staff Responsible", value="Not Assigned", key="new_officer")
    with col2:
        rate = st.number_input("Interest Rate (%)", value=14.0, key="new_rate")
        months = st.number_input("Term (Months)", min_value=1, value=1, key="new_months")
        disb_date = st.date_input("Disbursement Date", datetime(2026, 1, 15), key="new_disb")
    
    if st.button("💾 Save New Loan", type="primary"):
        if name and phone:
            total = amount + (amount * rate / 100 * months)
            due_date = disb_date + timedelta(days=30 * months)
            c.execute("""INSERT INTO loans (borrower_name, phone, amount, interest_rate, term_months, 
                          total_repayment, disbursement_date, due_date, loan_officer)
                         VALUES (?,?,?,?,?,?,?,?,?)""",
                      (name, phone, amount, rate, months, total, str(disb_date), str(due_date), officer))
            conn.commit()
            st.success(f"✅ Loan for **{name}** saved successfully!")
            st.rerun()
        else:
            st.error("Name and Phone are required")

with tab3:
    st.subheader("Loans Portfolio")
    search = st.text_input("🔍 Search Borrower", key="search_port")
    df = pd.read_sql_query("SELECT * FROM loans ORDER BY id ASC", conn)
    if not df.empty:
        if search:
            df = df[df['borrower_name'].str.contains(search, case=False)]
        df['balance'] = df['total_repayment'] - df.get('amount_paid', 0)
        df['penalty'] = df.apply(lambda x: calculate_penalty(x['due_date'], x['balance'], x.get('frozen', 0)), axis=1)
        df['total_now'] = df.apply(lambda x: x.get('frozen_balance', 0) if x.get('frozen', 0) else x['balance'] + x['penalty'], axis=1)
        df['status'] = df.apply(lambda x: "❄️ Frozen" if x.get('frozen', 0) else ("✅ Paid" if x['balance'] <= 1 else "Active"), axis=1)
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Manage Loan")
    manage_id = st.number_input("Loan ID", min_value=1, key="manage_id")

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("✏️ Load for Edit"):
            loan_data = pd.read_sql_query("SELECT * FROM loans WHERE id=?", conn, params=(manage_id,))
            if not loan_data.empty:
                st.session_state.edit_loan = loan_data.iloc[0]
                st.success("Loaded! Scroll down to edit")
    with col2:
        if st.button("❄️ Freeze / Unfreeze"):
            c.execute("UPDATE loans SET frozen = NOT frozen WHERE id=?", (manage_id,))
            conn.commit()
            st.success("Status updated!")
            st.rerun()
    with col3:
        if st.button("🗑️ Delete Loan", type="secondary"):
            if st.checkbox("Confirm Delete?"):
                c.execute("DELETE FROM loans WHERE id=?", (manage_id,))
                c.execute("DELETE FROM payments WHERE loan_id=?", (manage_id,))
                conn.commit()
                st.success("Loan deleted!")
                st.rerun()

    # Edit Form
    if 'edit_loan' in st.session_state:
        loan = st.session_state.edit_loan
        st.write(f"**Editing Loan ID: {loan['id']}**")
        col_a, col_b = st.columns(2)
        with col_a:
            new_name = st.text_input("Name", loan['borrower_name'], key="edit_name")
            new_phone = st.text_input("Phone", loan['phone'], key="edit_phone")
            new_amount = st.number_input("Amount", value=float(loan['amount']), key="edit_amount")
            new_officer = st.text_input("Officer", loan['loan_officer'], key="edit_officer")
        with col_b:
            new_rate = st.number_input("Rate (%)", value=float(loan['interest_rate']), key="edit_rate")
            new_months = st.number_input("Months", value=int(loan['term_months']), key="edit_months")
            new_disb = st.date_input("Disbursement Date", datetime.strptime(loan['disbursement_date'], '%Y-%m-%d'), key="edit_disb")
        
        if st.button("💾 Save Changes"):
            new_total = new_amount + (new_amount * new_rate / 100 * new_months)
            new_due = new_disb + timedelta(days=30 * new_months)
            c.execute("""UPDATE loans SET borrower_name=?, phone=?, amount=?, interest_rate=?, term_months=?, 
                         total_repayment=?, disbursement_date=?, due_date=?, loan_officer=? WHERE id=?""",
                      (new_name, new_phone, new_amount, new_rate, new_months, new_total, str(new_disb), str(new_due), new_officer, loan['id']))
            conn.commit()
            st.success("Loan updated successfully!")
            del st.session_state.edit_loan
            st.rerun()

with tab4:
    st.subheader("Record Payment")
    loan_id = st.number_input("Loan ID", min_value=1, key="pay_loan")
    pay_amount = st.number_input("Payment Amount (UGX)", min_value=1000, key="pay_amount")
    pay_date = st.date_input("Payment Date", datetime.now().date(), key="pay_date")
    if st.button("💰 Record Payment", type="primary"):
        c.execute("SELECT id FROM loans WHERE id=?", (loan_id,))
        if c.fetchone():
            pay_date_str = pay_date.strftime('%Y-%m-%d')
            c.execute("INSERT INTO payments (loan_id, amount, payment_date) VALUES (?,?,?)", (loan_id, pay_amount, pay_date_str))
            c.execute("UPDATE loans SET amount_paid = amount_paid + ? WHERE id=?", (pay_amount, loan_id))
            conn.commit()
            st.success(f"Payment recorded on {pay_date_str}")
        else:
            st.error("Loan ID not found")

with tab5:
    st.subheader("Download Client Statement")
    stmt_id = st.number_input("Loan ID", min_value=1, key="stmt_id")
    if st.button("📄 Generate & Download Statement"):
        try:
            loan = pd.read_sql_query("SELECT * FROM loans WHERE id=?", conn, params=(stmt_id,)).iloc[0]
            payments = pd.read_sql_query("SELECT * FROM payments WHERE loan_id=? ORDER BY payment_date", conn, params=(stmt_id,))
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", 'B', 16)
            pdf.cell(0, 10, "PROSPER MACRO SOLUTIONS LTD", ln=True, align='C')
            pdf.set_font("Arial", size=12)
            pdf.cell(0, 10, "Loan Statement", ln=True, align='C')
            pdf.ln(10)
            pdf.cell(0, 10, f"Borrower: {loan['borrower_name']}", ln=True)
            pdf.cell(0, 10, f"Phone: {loan['phone']}", ln=True)
            pdf.cell(0, 10, f"Loan ID: {loan['id']}", ln=True)
            pdf.cell(0, 10, f"Principal: UGX {loan['amount']:,.0f}", ln=True)
            pdf.cell(0, 10, f"Total Due: UGX {loan['total_repayment']:,.0f}", ln=True)
            pdf.ln(10)
            pdf.cell(0, 10, "Payments:", ln=True)
            for _, p in payments.iterrows():
                pdf.cell(0, 10, f"{p['payment_date']} - UGX {p['amount']:,.0f}", ln=True)
            pdf_output = f"Statement_Loan_{stmt_id}.pdf"
            pdf.output(pdf_output)
            with open(pdf_output, "rb") as f:
                st.download_button("⬇️ Download PDF", f, file_name=pdf_output, mime="application/pdf")
        except:
            st.error("Loan not found")

st.sidebar.success("✅ Logged in as Admin")
if st.sidebar.button("Logout"):
    st.session_state.logged_in = False
    st.rerun()