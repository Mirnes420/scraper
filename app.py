import sys
import asyncio
import time  
import streamlit as st
import pandas as pd
import subprocess
import os
import json

#-------------------------------------------------------------------------------#
# SYSTEM CONFIG
#-------------------------------------------------------------------------------#
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

st.set_page_config(page_title="LeadGen Pro 2026", layout="wide")


# This ensures the app doesn't show old leads from previous users/sessions
if "logged_in" not in st.session_state:
    st.session_state["logged_in"] = False
    if os.path.exists("leads_with_emails.csv"):
        os.remove("leads_with_emails.csv")

#-------------------------------------------------------------------------------#
# SIDEBAR: CREDENTIALS & DEBUG
#-------------------------------------------------------------------------------#
# --- LOGIN SCREEN ---
if not st.session_state["logged_in"]:
    st.title("🔒 Outreach Login")
    with st.form("login_form"):
        email = st.text_input("Gmail Address")
        app_password = st.text_input("Gmail App Password", type="password")
        sender_name = st.text_input("Your Name")
        company = st.text_input("Company Name")
        submit = st.form_submit_button("Enter Dashboard")

        if submit:
            if email and app_password and sender_name:
                # Store everything in session
                st.session_state["email_val"] = email
                st.session_state["pass_val"] = app_password
                st.session_state["name_val"] = sender_name
                st.session_state["comp_val"] = company
                st.session_state["logged_in"] = True
                st.session_state["user_id"] = email
                st.rerun()
            else:
                st.error("Please fill in all required fields.")
    st.stop() # Prevents the rest of the app from loading

# --- DASHBOARD (Only visible if logged_in is True) ---
st.sidebar.success(f"Logged in as: {st.session_state.name_val}")
if st.sidebar.button("Logout & Wipe Data"):
    if os.path.exists("leads_with_emails.csv"):
        os.remove("leads_with_emails.csv")
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

#-------------------------------------------------------------------------------#
# MAIN UI: SEARCH PARAMETERS
#-------------------------------------------------------------------------------#
st.title("🚀 Lead Generator & Outreach")

col1, col2, col3 = st.columns(3)
with col1:
    st.text_input("Business Type", value="Software Development", key="cat_val")
with col2:
    st.text_input("Location", value="Munich", key="city_val")
with col3:
    st.number_input("Count", min_value=1, max_value=50, value=2, key="count_val")

#-------------------------------------------------------------------------------#
# EMAIL TEMPLATE
#-------------------------------------------------------------------------------#
st.header("📧 Email Template")
st.info("Use [Business Name] as placeholder.")
st.text_input("Subject", value="Question regarding [Business Name]", key="subj_val")
email_content = st.text_area("Email Content", height=200, key="body_val", 
             value=f"""Hello [Business Name],

my name is {st.session_state.name_val} from {st.session_state.comp_val}. I saw your business in {st.session_state.city_val} and would like to help you.

Best regards,
{st.session_state.name_val}""")


#-------------------------------------------------------------------------------#
# SCRAPER EXECUTION
#-------------------------------------------------------------------------------#
# --- TIME TRACKING START ---
start_time = time.time()

if st.button("🚀 Start Scraper & Outreach"):
    
    if not st.session_state.email_val or not st.session_state.name_val:
        st.error("❌ Fill in the sidebar credentials!")
    else:
        output_file = "leads_with_emails.csv"
        query = f"{st.session_state.cat_val} in {st.session_state.city_val}"
        email_data = {"subject": st.session_state.subj_val, "body": st.session_state.body_val}

        cmd = [
            sys.executable, "scraper.py", 
            str(st.session_state.count_val),
            output_file, 
            st.session_state.cat_val,
            st.session_state.city_val,
            query, 
            st.session_state.email_val,
            st.session_state.pass_val, 
            st.session_state.name_val,
            st.session_state.comp_val, 
            json.dumps(email_data),
            str(st.session_state.user_id)
        ]

        with st.spinner("Scraping and processing leads..."):
            try:
                subprocess.run(cmd,text=True, stdout=None, stderr=None, check=True)
            except subprocess.CalledProcessError as e:
                st.error("Backend Error")
                st.code(e.stderr)


# --- TIME TRACKING END ---
end_time = time.time()
duration = end_time - start_time

#-------------------------------------------------------------------------------#
# THE "MISSING" BLOCK: SHOW & EDIT EMAILS
#-------------------------------------------------------------------------------#
output_file = "leads_with_emails.csv"

if os.path.exists(output_file):
    st.divider()
    st.header("✅ Outreach Summary")
    
    df = pd.read_csv(output_file)
    
    if not df.empty:
        # Filter for valid emails
        sent_df = df[df['email'].notna() & (df['email'] != "N/A")]
        
        if not sent_df.empty:
            st.success(f"Successfully processed {len(sent_df)} emails in {duration:.2f} seconds.")
            
            # Show ONLY the clean list of recipients
            st.subheader("📩 Recipient List")
            for index, row in sent_df.iterrows():
                # Displaying each one in a clean, professional line
                st.write(f"✔️ **{row['name']}** — *{row['email']}*")
                
        else:
            st.warning("No valid email addresses were found to send to.")
    else:
        st.warning("No leads were generated.")
