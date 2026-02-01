import csv
import smtplib
import time
from email.message import EmailMessage

# --- CONFIGURATION ---



#-------------------------------------------------------------------------------#``
# EMAIL SENDING ENGINE (DYNAMIC)
#-------------------------------------------------------------------------------#
def send_email(email, business_name, user_email, app_password, email_content, city):
    """Sends a personalized email using credentials provided from the frontend."""
    if not email or email == "N/A":
        return
    
    subject = str(email_content.get('subject', '')).strip()
    body = str(email_content.get('body', '')).strip()
    to_email = str(email).strip()
    from_email = str(user_email).strip()
    subject = email_content['subject'].replace("[Business Name]", business_name).replace("[Location]", city)
    body = email_content['body'].replace("[Business Name]", business_name).replace("[Location]", city)
                        
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = from_email
    msg['To'] = to_email
    msg.set_content(body)

    try:
        # Use Port 587 with starttls for better compatibility in 2026
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(from_email, app_password)
            server.send_message(msg)
            print(f"Email successfully sent to {business_name} ({to_email})")
            return True
    except Exception as e:
        print(f"Failed to send to {to_email}: {e}")
        return False
    
