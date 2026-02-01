import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

def get_or_create_global_lead(lead_data):
    """Checks if lead exists globally; updates or creates it."""
    # Upsert: If email exists, update last_scraped. If not, insert.
    response = supabase.table("global_leads").upsert({
        "name": lead_data['name'],
        "email": lead_data['email'],
        "website": lead_data.get('website'),
        "category": lead_data.get('category'),
        "city": lead_data.get('city'),
        "status": "verified",
        "last_scraped": "now()"
    }, on_conflict="email").execute()
    
    return response.data[0]['id']

def link_lead_to_user(user_id, lead_id, lead_name):
    """Links a global lead to a specific user's dashboard."""
    supabase.table("user_leads").upsert({
        "user_id": user_id,
        "lead_id": lead_id,
        "lead_name": lead_name,
        "status": "pending"
    }, on_conflict="user_id,lead_id").execute()

def lead_is_new_for_this_sender(business_name, user_id):
    """
    Queries Supabase to see if this specific user has a record 
    for this business name in their user_leads table.
    """
    try:
        # Check if a row exists with this user_id and lead_name
        response = supabase.table("user_leads") \
            .select("id") \
            .eq("user_id", user_id) \
            .eq("lead_name", business_name) \
            .execute()
        
        # If the list in response.data is empty, the lead is NEW
        return len(response.data) == 0
    except Exception as e:
        print(f"⚠️ Database Check Error: {e}")
        # In case of error, we assume it's new so the scraper doesn't stop
        return True
    
def check_db_for_name(business_name):
    """
    Checks the global database for an existing lead by name.
    Returns the lead data if found, otherwise None.
    """
    try:
        response = supabase.table("global_leads") \
            .select("id, email, website") \
            .eq("name", business_name) \
            .execute()
        
        if response.data:
            # Return the first match (should be unique by name/email logic)
            return response.data[0] 
        return None
    except Exception as e:
        print(f"⚠️ Global DB Check Error: {e}")
        return None