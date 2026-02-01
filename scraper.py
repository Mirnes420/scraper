import os
import io
import re
import sys
import csv
import time
import json
import sqlite3
import pandas as pd
from send_autoemail import send_email
from playwright.sync_api import sync_playwright
from database import get_or_create_global_lead, link_lead_to_user, lead_is_new_for_this_sender, check_db_for_name

# This forces the script to ignore the terminal's old encoding 
# and use UTF-8 for all print statements.
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# --- EMAIL EXTRACTION ---

def extract_email_from_page(page):
    """Scans the whole page source for email patterns, including mailto links."""
    email_regex = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    try:
        content = page.content()
        emails = re.findall(email_regex, content)
        # Filter out junk like image extensions
        valid_emails = [e for e in emails if not e.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.pdf'))]
        return list(set(valid_emails)) 
    except:
        return []


def find_email_on_website(browser, url):
    """Visits the business website and looks for emails with image blocking for speed."""
    if not url or url == "N/A": return "N/A"
    
    context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    page = context.new_page()
    
    # --- ADDED: BLOCK IMAGES & CSS FOR SPEED ---
    # This prevents the browser from wasting time/bandwidth on visual assets
    page.route("**/*.{png,jpg,jpeg,svg,gif,webp,pdf,css,woff,woff2}", lambda route: route.abort())
    
    email_found = "N/A"
    
    try:
        # Reduced timeout to 15s because if it hasn't loaded by then, it's a "slow" lead
        page.goto(url, timeout=15000, wait_until="domcontentloaded")
        
        # --- COOKIE CRUSHER ---
        # --- IMPROVED COOKIE CRUSHER ---
        try:
            # Common IDs and Classes for global cookie providers (OneTrust, CookieBot, etc.)
            # Bosnian, English, and German terms included
            universal_selector = (
                'button:has-text("Accept"), button:has-text("Akzeptieren"), '
                'button:has-text("OK"), button:has-text("Allow"), '
                'button:has-text("Slažem se"), button:has-text("Prihvati"), '
                '[id*="cookie-accept"], [class*="accept-button"], [id*="consent-allow"]'
            )
            
            # Try to click the first visible button immediately
            cookie_btn = page.locator(universal_selector).first
            if cookie_btn.is_visible(timeout=1000): # Only wait 1 second max
                cookie_btn.click(force=True, timeout=2000)
                print(f"   [+] Cookie banner bypassed.")
        except Exception:
            # If no banner, don't waste time—just keep moving
            pass

        # 1. Check homepage
        results = extract_email_from_page(page)
        
        # 2. Deep Search (Legal/Contact)
        if not results:
            # German-market specific pages added: "Datenschutz" and "Legal"
            for selector in ['a:has-text("Impressum")', 'a:has-text("Kontakt")', 'a:has-text("Contact")', 'a:has-text("Legal")']:
                link = page.locator(selector).first
                if link.is_visible():
                    link.click()
                    # Wait for the next page to actually load before scraping
                    page.wait_for_load_state("domcontentloaded")
                    results = extract_email_from_page(page)
                    if results: break
        
        if results: 
            email_found = results[0]
    except Exception as e:
        print(f"Error scraping {url}: {e}")
    finally:
        page.close() # Close page specifically
        context.close()
    return email_found

# --- MAIN SCRAPER ---

def run_scraper(max_results, output_file, category, city, search_query, sender_email, user_id):
    # Initialize CSV with Headers
    if os.path.exists(output_file):
        os.remove(output_file)
    pd.DataFrame(columns=["name", "website", "email"]).to_csv(output_file, index=False)
    print("------------------------------------------------------------------------------------------------------------")
    print("search query", search_query)
    print("------------------------------------------------------------------------------------------------------------")
    count_to_add = 0
    results_list = []
    visited_companies = set() # To track which map cards we clicked
    collected_emails = set()  # To track emails and prevent duplicates
    results_count = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Standard context
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()
        
        # Go to Maps
        page.goto("https://www.google.com/maps", timeout=60000)

        # --- FLEXIBLE GOOGLE COOKIE WALL HANDLER ---
        try:
            # Wait for search box OR any accept button
            page.wait_for_selector('button[aria-label*="Accept"], button:has-text("Accept all"), button:has-text("Alle akzeptieren"), input#searchboxinput', timeout=10000)
            
            accept_btn = page.locator('button:has-text("Accept all"), button:has-text("Alle akzeptieren"), button:has-text("I agree")').first
            if accept_btn.is_visible():
                accept_btn.click()
                page.wait_for_load_state("networkidle")
                time.sleep(1)
        except:
            print("No cookie wall found, checking for search box...")

        # --- SEARCH EXECUTION ---
        try:
            search_box = page.locator("input#searchboxinput")
            if not search_box.is_visible():
                search_box = page.locator("input").first
            
            search_box.fill(str(search_query))
            page.keyboard.press("Enter")
            page.wait_for_selector('div[role="feed"]', timeout=20000)
        except Exception as e:
            print(f"Error finding search box: {e}")
            browser.close()
            return []

        # --- EXTRACTION LOOP ---
        # Loop continues until we have enough EMAILS, not just companies
        while results_count < max_results:
            cards = page.locator('div[role="article"]').all()
            if not cards: break

            for card in cards:
                if results_count >= max_results: break
                
                try:
                    # 1. Get the name safely
                    name_locator = card.locator('div.fontHeadlineSmall').first
                    if not name_locator.is_visible(): continue
                    name = name_locator.inner_text().strip()
                    
                    if name in visited_companies: continue
                    visited_companies.add(name)

                    # --- NEW: PERMISSION CHECK ---
                    # Check if this specific user_id already "owns" or has contacted this lead
                    if not lead_is_new_for_this_sender(name, user_id):
                        print(f"⏭️  [USER SKIP] {name} already exists in your Supabase dashboard.")
                        continue

                    # 2. THE SMART CHECK: Check Global DB before clicking
                    existing_lead = check_db_for_name(name)
                    
                    if existing_lead and existing_lead['email'] != "N/A":
                        print(f"⚡ [DB HIT] {name} - Reusing global data.")
                        email = existing_lead['email']
                        website = existing_lead['website']
                        global_id = existing_lead['id']
                        
                        
                        # Save to CSV for the current session
                        lead = {"name": name, "website": website, "email": email}
                        pd.DataFrame([lead]).to_csv(output_file, mode='a', header=False, index=False)
                        results_count += 1
                        continue 

                    # 3. THE HARD WAY: If not in DB, click and scrape
                    print(f"🔍 Not in DB [SCRAPE] Processing: {name}")
                    card.click()
                    try:
                        page.wait_for_selector('a[data-item-id="authority"]', timeout=2000)
                    except:
                        continue
                        
                    time.sleep(1)

                    web_locator = page.locator('a[data-item-id="authority"]').first
                    website = web_locator.get_attribute("href") if web_locator.count() > 0 else "N/A"

                    email = find_email_on_website(browser, website)
                    
                    if email != "N/A" and email not in collected_emails:
                        # Inside your scraper loop after finding a lead:
                        lead_info = {
                            "name": name,
                            "email": email,
                            "website": website,
                            "category": category,
                            "city": city
                        }

                        # 1. Save to Global DB and get the ID
                        global_id = get_or_create_global_lead(lead_info)

                        # 2. Link to the User (use the session user_id from Streamlit)
                        link_lead_to_user(user_id, global_id, name)
                        lead = {"name": name, "website": website, "email": email}
                        pd.DataFrame([lead]).to_csv(output_file, mode='a', header=False, index=False)
                        
                        collected_emails.add(email)
                        results_list.append(lead)
                        results_count += 1
                        print(f"✨ [{results_count}/{max_results}] NEW & LOGGED: {name}")

                except Exception as e:
                    print(f"Error processing card: {e}")
                    continue
            # Scroll feed to load more
            feed = page.locator('div[role="feed"]')
            if feed.count() > 0:
                feed.evaluate("el => el.scrollBy(0, 1000)")
                time.sleep(2)
            else:
                # If feed is missing, we are probably lost or at the end
                break
        
        browser.close()
        return results_list


if __name__ == "__main__":
    
    # 1. Define configuration
    if len(sys.argv) > 5:
        count          = int(sys.argv[1])
        output_file    = sys.argv[2]
        category       = sys.argv[3]
        city           = sys.argv[4]
        query          = sys.argv[5] 
        sender_email   = sys.argv[6]
        app_password   = sys.argv[7]
        sender_name    = sys.argv[8]
        company_name   = sys.argv[9]
        email_data     = json.loads(sys.argv[10])
        user_id = sys.argv[11]
        
    else:
        count = 2
        output_file = "testmail.csv" # Matches your email script's target
        category = "plumbers"
        city = "Berlin"
        query = "plumbers in Berlin"

    # 2. Run the Scraper
    print(f"🚀 Starting scrape for {query}...")
    run_scraper(count, output_file, category, city, query, sender_email, user_id)
    print(f"✅ Scraping complete. Leads saved to {output_file}.")

    # 3. Trigger Emails Automatically
    print(f"📧 Starting email sequence from {output_file}...")
    
    
    if os.path.exists(output_file):
        with open(output_file, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                name = row['name']
                email = row['email'].strip()
                
                if email and email != "N/A":
                    # Calling your imported function
                    
                    send_email(
                    email=row['email'],           # to_email
                    business_name=row['name'],            # business_name
                    user_email=sender_email,    # your gmail
                    app_password=app_password,    # your app pass
                    email_content=email_data,  # the JSON dict, 
                    city=city
                )
                    # 2026 Deliverability Tip: 5-10 seconds is safer for Gmail
                    time.sleep(7) 
                else:
                    print(f"Skipping {name}: No email found.")
    else:
        print(f"Error: {output_file} not found. No emails sent.")