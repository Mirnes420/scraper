import pytest
import uuid
import sys
from playwright.sync_api import sync_playwright
from scraper import extract_email_from_page
from database import check_db_for_name, get_or_create_global_lead, link_lead_to_user, lead_is_new_for_this_sender

# --- 1. TEST EMAIL EXTRACTION ---
def test_email_regex():
    """Tests if our regex catches emails but ignores junk/images."""
    class MockPage:
        def content(self):
            return """
            <html>
                <body>
                    Contact us at info@business.com or support@company.de
                    Ignore this: image@test.png and style@web.css
                </body>
            </html>
            """
    
    page = MockPage()
    emails = extract_email_from_page(page)
    
    assert "info@business.com" in emails
    assert "support@company.de" in emails
    assert "image@test.png" not in emails
    print("\n✅ Email Regex Test Passed")

# --- 2. TEST SUPABASE GLOBAL & USER LOGIC ---
def test_supabase_integration():
    """Tests the full cloud flow: Global Insert -> User Linking -> Permission Check."""
    # Create unique data so we don't hit "Unique Constraint" errors every time we test
    unique_id = str(uuid.uuid4())[:8]
    test_name = f"Test Corp {unique_id}"
    test_email = f"contact@{unique_id}.com"
    test_user = "test_user_account@gmail.com"
    
    lead_data = {
        "name": test_name,
        "website": "http://test.com",
        "email": test_email,
        "category": "Testing",
        "city": "Berlin"
    }

    print(f"\n[1] Testing Global Upsert for: {test_name}")
    global_id = get_or_create_global_lead(lead_data)
    assert global_id is not None
    
    print("[2] Testing Global Retrieval...")
    res = check_db_for_name(test_name)
    assert res is not None
    assert res['email'] == test_email
    
    print(f"[3] Linking lead to user: {test_user}")
    link_lead_to_user(test_user, global_id, test_name)
    
    print("[4] Testing Permission Check (Should now be False/Not New)...")
    is_new = lead_is_new_for_this_sender(test_name, test_user)
    assert is_new is False
    
    print("✅ Supabase Integration Test Passed")

# --- 3. TEST LIVE SCRAPE (Lightweight) ---
def test_live_site_access():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        try:
            response = page.goto("https://example.com", timeout=10000)
            assert response.status == 200
            print("✅ Live Site Access Test Passed")
        finally:
            browser.close()

if __name__ == "__main__":
    # Run them all
    try:
        test_email_regex()
        test_supabase_integration()
        test_live_site_access()
        print("\n🚀 ALL TESTS PASSED SUCCESSFULLY")
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)