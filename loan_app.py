import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import io

# ====================== DATABASE ======================
conn = sqlite3.connect('loans.db', check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS users (
             id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, role TEXT, full_name TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS loans (
             id INTEGER PRIMARY KEY, borrower_name TEXT, phone TEXT, amount REAL,
             interest_rate REAL, term_months INTEGER, total_repayment REAL,
             disbursement_date TEXT, due_date TEXT, amount_paid REAL DEFAULT 0,
             loan_officer TEXT, frozen INTEGER DEFAULT 0,
             is_balance_frozen INTEGER DEFAULT 0, frozen_balance REAL DEFAULT 0)''')

c.execute('''CREATE TABLE IF NOT EXISTS payments (
             id INTEGER PRIMARY KEY, loan_id INTEGER, amount REAL, payment_date TEXT)''')

c.execute("INSERT OR IGNORE INTO users (username, password, role, full_name) VALUES ('admin', '123456', 'Admin', 'System Administrator')")
c.execute("INSERT OR IGNORE INTO users (username, password, role, full_name) VALUES ('officer1', '1234', 'Officer', 'John Officer')")
conn.commit()

# ====================== HELPER FUNCTIONS ======================
def calculate_balance(total, paid):
    return max(0, total - paid)

def calculate_penalty(due_date_str, balance, frozen, is_balance_frozen):
    if is_balance_frozen or frozen or balance <= 0:
        return 0
    try:
        due = datetime.strptime(due_date_str, '%Y-%m-%d').date()
        today = datetime.now().date()
        grace_end = due + timedelta(days=10)
        if today <= grace_end: return 0
        days_late = (today - grace_end).days
        return round(balance * 0.01 * days_late)
    except:
        return 0

# ====================== LOGIN ======================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_role = None
    st.session_state.username = None

if not st.session_state.logged_in:
    st.title("🔐 PROSPER MACRO SOLUTIONS LTD")
    st.subheader("Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        user = pd.read_sql_query("SELECT * FROM users WHERE username=? AND password=?", conn, params=(username, password))
        if not user.empty:
            st.session_state.logged_in = True
            st.session_state.user_role = user.iloc[0]['role']
            st.session_state.username = username
            st.rerun()
        else:
            st.error("Invalid credentials")
    st.stop()

# ====================== APP ======================
st.set_page_config(page_title="Prosper Macro Loans", layout="wide")
st.title("💼 PROSPER MACRO SOLUTIONS LTD")
st.subheader(f"Loan Management System | {st.session_state.username} ({st.session_state.user_role})")

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["📊 Dashboard", "📝 New Loan", "📋 Portfolio", "💰 Record Payment", "📋 Reports", "✏️ Manage Loan"])

# ====================== DASHBOARD ======================
with tab1:
    st.subheader("Business Dashboard")
    df = pd.read_sql_query("SELECT * FROM loans", conn)
    if not df.empty:
        df['balance'] = df.apply(lambda x: calculate_balance(x['total_repayment'], x['amount_paid']), axis=1)
        df['penalty'] = df.apply(lambda x: calculate_penalty(x['due_date'], x['balance'], x['frozen'], x.get('is_balance_frozen', 0)), axis=1)
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Disbursed", f"UGX {df['amount'].sum():,.0f}")
        col2.metric("Outstanding", f"UGX {df['balance'].sum():,.0f}")
        col3.metric("Overdue Loans", len(df[df['penalty'] > 0]))
        col4.metric("Total Loans", len(df))
        st.dataframe(df[['id','borrower_name','amount','balance','penalty','loan_officer']], use_container_width=True, hide_index=True)

# ====================== NEW LOAN ======================
with tab2:
    st.subheader("Create New Loan")
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("Borrower Name *")
        phone = st.text_input("Phone Number *")
        amount = st.number_input("Loan Amount (UGX)", min_value=10000, value=100000, step=5000)
        officer = st.text_input("Loan Officer", value=st.session_state.username)
    with col2:
        rate = st.number_input("Interest Rate (%)", value=14.0, step=0.5)
        months = st.number_input("Term (Months)", min_value=1, value=1)
        disb_date = st.date_input("Disbursement Date", datetime.now().date())
    
    if st.button("💾 Save New Loan", type="primary"):
        if name and phone:
            total = amount * (1 + (rate / 100) * months)
            due_date = disb_date + timedelta(days=30 * months)
            c.execute("""INSERT INTO loans (borrower_name, phone, amount, interest_rate, term_months, 
                         total_repayment, disbursement_date, due_date, loan_officer)
                         VALUES (?,?,?,?,?,?,?,?,?)""", 
                      (name, phone, amount, rate, months, total, str(disb_date), str(due_date), officer))
            conn.commit()
            st.success(f"✅ Loan for **{name}** created!")
            st.rerun()

# ====================== PORTFOLIO (Full Detailed View) ======================
with tab3:
    st.subheader("Loans Portfolio")
    df = pd.read_sql_query("SELECT * FROM loans ORDER BY id ASC", conn)
    
    if not df.empty:
        df['balance'] = df.apply(lambda x: calculate_balance(x['total_repayment'], x['amount_paid']), axis=1)
        df['penalty'] = df.apply(lambda x: calculate_penalty(x['due_date'], x['balance'], x['frozen'], x.get('is_balance_frozen', 0)), axis=1)
        df['total_due'] = df['balance'] + df['penalty']
        
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        # Export Button
        if st.button("📥 Export Portfolio to Excel"):
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            output.seek(0)
            st.download_button("⬇️ Download Full Portfolio", output, "full_portfolio.xlsx", 
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    else:
        st.info("No loans found.")

# ====================== RECORD PAYMENT ======================
with tab4:
    st.subheader("Record Payment")
    col1, col2 = st.columns(2)
    with col1:
        loan_id = st.number_input("Loan ID", min_value=1)
        pay_amount = st.number_input("Payment Amount (UGX)", min_value=1000)
    with col2:
        pay_date = st.date_input("Payment Date", datetime.now().date())
    
    if st.button("💰 Record Payment", type="primary"):
        c.execute("SELECT id FROM loans WHERE id=?", (loan_id,))
        if c.fetchone():
            pay_date_str = pay_date.strftime('%Y-%m-%d')
            c.execute("INSERT INTO payments (loan_id, amount, payment_date) VALUES (?,?,?)", (loan_id, pay_amount, pay_date_str))
            c.execute("UPDATE loans SET amount_paid = amount_paid + ? WHERE id=?", (pay_amount, loan_id))
            conn.commit()
            st.success("✅ Payment recorded!")
            st.rerun()
        else:
            st.error("Loan ID not found")

# ====================== REPORTS (Clean Summary View) ======================
with tab5:
    st.subheader("Reports & Statements")
    report_type = st.selectbox("Select Report", ["Portfolio Summary", "Overdue Loans", "Loan Statement"])
    
    if report_type == "Loan Statement":
        stmt_id = st.number_input("Enter Loan ID", min_value=1)
        if st.button("Generate Statement"):
            loan = pd.read_sql_query("SELECT * FROM loans WHERE id=?", conn, params=(stmt_id,))
            payments = pd.read_sql_query("SELECT * FROM payments WHERE loan_id=? ORDER BY payment_date DESC", conn, params=(stmt_id,))
            if not loan.empty:
                st.dataframe(loan, hide_index=True)
                st.subheader("Payment History")
                st.dataframe(payments, hide_index=True)
    
    elif report_type == "Overdue Loans":
        df = pd.read_sql_query("SELECT * FROM loans", conn)
        if not df.empty:
            df['balance'] = df.apply(lambda x: calculate_balance(x['total_repayment'], x['amount_paid']), axis=1)
            df['penalty'] = df.apply(lambda x: calculate_penalty(x['due_date'], x['balance'], x['frozen'], x.get('is_balance_frozen', 0)), axis=1)
            overdue = df[df['penalty'] > 0].copy()
            if not overdue.empty:
                st.dataframe(overdue, use_container_width=True, hide_index=True)
            else:
                st.success("🎉 No overdue loans at the moment!")
    else:  # Portfolio Summary - Clean View
        df = pd.read_sql_query("SELECT * FROM loans", conn)
        if not df.empty:
            df['balance'] = df.apply(lambda x: calculate_balance(x['total_repayment'], x['amount_paid']), axis=1)
            df['penalty'] = df.apply(lambda x: calculate_penalty(x['due_date'], x['balance'], x['frozen'], x.get('is_balance_frozen', 0)), axis=1)
            df['total_due'] = df['balance'] + df['penalty']
            
            display_cols = ['id', 'borrower_name', 'phone', 'amount', 'balance', 'penalty', 'total_due', 'loan_officer']
            st.dataframe(df[display_cols], use_container_width=True, hide_index=True)
            
            if st.button("📥 Export Summary to Excel"):
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df[display_cols].to_excel(writer, index=False)
                output.seek(0)
                st.download_button("⬇️ Download Summary Report", output, "portfolio_summary.xlsx", 
                                 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ====================== MANAGE LOAN ======================
with tab6:
    st.subheader("Manage Loan - Edit / Freeze")
    manage_id = st.number_input("Loan ID", min_value=1, key="manage_id")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("❄️ Freeze / Unfreeze Loan"):
            c.execute("UPDATE loans SET frozen = NOT frozen WHERE id=?", (manage_id,))
            conn.commit()
            st.success(f"Loan {manage_id} freeze status updated!")
            st.rerun()
    with col2:
        if st.button("🔒 Freeze Current Balance"):
            loan = pd.read_sql_query("SELECT * FROM loans WHERE id=?", conn, params=(manage_id,))
            if not loan.empty:
                current_balance = calculate_balance(loan.iloc[0]['total_repayment'], loan.iloc[0]['amount_paid'])
                c.execute("UPDATE loans SET is_balance_frozen=1, frozen_balance=? WHERE id=?", (current_balance, manage_id))
                conn.commit()
                st.success(f"✅ Balance frozen at UGX {current_balance:,.0f}")
                st.rerun()
    with col3:
        if st.button("🔓 Unfreeze Balance"):
            c.execute("UPDATE loans SET is_balance_frozen=0, frozen_balance=0 WHERE id=?", (manage_id,))
            conn.commit()
            st.success("Balance unfrozen!")
            st.rerun()

    if st.button("✏️ Load Loan for Editing"):
        loan_data = pd.read_sql_query("SELECT * FROM loans WHERE id=?", conn, params=(manage_id,))
        if not loan_data.empty:
            st.session_state.edit_loan = loan_data.iloc[0].to_dict()
            st.success("Loan loaded! Scroll down to edit.")

    if 'edit_loan' in st.session_state:
        loan = st.session_state.edit_loan
        st.write(f"**Editing Loan ID: {loan['id']} - {loan['borrower_name']}**")
        col1, col2 = st.columns(2)
        with col1:
            new_name = st.text_input("Borrower Name", loan['borrower_name'])
            new_phone = st.text_input("Phone Number", loan['phone'])
            new_amount = st.number_input("Loan Amount", value=float(loan['amount']))
            new_officer = st.text_input("Loan Officer", loan['loan_officer'])
        with col2:
            new_rate = st.number_input("Interest Rate (%)", value=float(loan['interest_rate']))
            new_months = st.number_input("Term (Months)", value=int(loan['term_months']))
            new_disb = st.date_input("Disbursement Date", datetime.strptime(loan['disbursement_date'], '%Y-%m-%d').date())
            new_due = st.date_input("Due Date", datetime.strptime(loan['due_date'], '%Y-%m-%d').date())
            new_frozen = st.checkbox("Loan Frozen", value=bool(loan.get('frozen', 0)))
        
        if st.button("💾 Save Changes", type="primary"):
            new_total = new_amount * (1 + (new_rate / 100) * new_months)
            c.execute("""UPDATE loans SET borrower_name=?, phone=?, amount=?, interest_rate=?, 
                        term_months=?, total_repayment=?, disbursement_date=?, due_date=?, 
                        loan_officer=?, frozen=? WHERE id=?""",
                      (new_name, new_phone, new_amount, new_rate, new_months, new_total, 
                       str(new_disb), str(new_due), new_officer, int(new_frozen), manage_id))
            conn.commit()
            st.success("✅ Loan updated successfully!")
            del st.session_state.edit_loan
            st.rerun()

st.sidebar.success(f"👤 {st.session_state.username} ({st.session_state.user_role})")
if st.sidebar.button("Logout"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()