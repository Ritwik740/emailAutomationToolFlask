import os
import time
from datetime import datetime
import sqlite3
import smtplib
from email.mime.text import MIMEText

from app import get_db_connection  # Replace 'your_app' with actual module if needed

def followup_scheduler():
    print("Follow-up scheduler started")
    loop_count = 0
    while True:
        loop_count += 1
        print(f"Scheduler check #{loop_count} at {datetime.now()}")
        try:
            conn = get_db_connection()
            
            # Set row_factory only if SQLite is used
            is_production = os.environ.get('FLASK_ENV') == 'production'
            if not is_production:
                conn.row_factory = sqlite3.Row
            
            c = conn.cursor()
            now = datetime.now()
            current_time = now.strftime("%Y-%m-%d %H:%M:%S")
            print(f"Current time for comparison: {current_time}")

            # Check for table existence (SQLite specific)
            if not is_production:
                c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='emails'")
                if not c.fetchone():
                    print("Error: 'emails' table does not exist in the database.")
                    time.sleep(60)
                    continue

            # Query for pending follow-ups
            if is_production:
                query = '''
                SELECT 
                    emails.id, 
                    emails.sender_email, 
                    emails.sender_password, 
                    emails.recipient_email, 
                    emails.recipient_name, 
                    emails.subject, 
                    emails.followup_body
                FROM 
                    emails
                JOIN 
                    users ON emails.id = users.id
                WHERE 
                    emails.followup_date <= %s
                    AND emails.followup_sent = 0
                    AND emails.followup_body IS NOT NULL
                    AND users.subscription_end_date >= CURRENT_TIMESTAMP
                '''
                    # SELECT id, sender_email, sender_password, recipient_email, recipient_name, subject, followup_body
                    # FROM emails 
                    # WHERE followup_date <= %s 
                    # AND followup_sent = 0
                    # AND followup_body IS NOT NULL
            else:
                query = '''
                    SELECT id, sender_email, sender_password, recipient_email, recipient_name, subject, followup_body
                    FROM emails 
                    WHERE followup_date <= ? 
                    AND followup_sent = 0
                    AND followup_body IS NOT NULL
                '''

            c.execute(query, (current_time,))
            emails_to_followup = c.fetchall()
            print(f"Found {len(emails_to_followup)} emails due for follow-up")
            
            for email in emails_to_followup:
                email_id = email['id']
                sender_email = email['sender_email']
                sender_password = email['sender_password']
                recipient_email = email['recipient_email']
                recipient_name = email['recipient_name']
                subject = email['subject']
                followup_body = email['followup_body']

                print(f"Sending follow-up to {recipient_email} from {sender_email}")
                try:
                    msg = MIMEText(f"Hello {recipient_name},\n\n{followup_body}")
                    msg['Subject'] = f"Follow-up: {subject}"
                    msg['From'] = sender_email
                    msg['To'] = recipient_email

                    with smtplib.SMTP('smtp.gmail.com', 587) as server:
                        server.starttls()
                        server.login(sender_email, sender_password)
                        server.sendmail(sender_email, recipient_email, msg.as_string())

                    # Update followup_sent status
                    if is_production:
                        c.execute('UPDATE emails SET followup_sent = %s WHERE id = %s', (1, email_id))
                    else:
                        c.execute('UPDATE emails SET followup_sent = ? WHERE id = ?', (1, email_id))
                    
                    conn.commit()
                    print(f"✅ Successfully sent follow-up to {recipient_email}")
                except Exception as e:
                    print(f"❌ Error sending follow-up to {recipient_email}: {str(e)}")

            conn.close()
            time.sleep(60)

        except Exception as e:
            print(f"🔥 Error in follow-up scheduler: {str(e)}")
            time.sleep(30)
            
            
if __name__ == "__main__":
    followup_scheduler()
