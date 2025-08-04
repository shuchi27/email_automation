import os
import base64
import re
import csv
import smtplib
from email.mime.text import MIMEText
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
#import sqlite3
from pymongo import MongoClient
import re
from config import VOLUNTEERS, SENDER_EMAIL, APP_PASSWORD, DB_NAME, SCOPES
from urllib.parse import quote_plus
from datetime import datetime
import schedule
import time
import logging
from logging.handlers import RotatingFileHandler
from datetime import timedelta

# Create logs directory if it doesn't exist
if not os.path.exists("logs"):
    os.makedirs("logs")

log_file = "logs/automation.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s — %(levelname)s — %(message)s",
    handlers=[
        RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=3),
        logging.StreamHandler()
    ]
)


SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/calendar'
]
#SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# === CONFIG ===
VOLUNTEERS = ["shuchi@lead4earth.org"]
SENDER_EMAIL = "shuchibshah27@gmail.com"
APP_PASSWORD = "cofo lwmh cnvo isgv"  # Use Gmail App Password


def init_db():
    username = "shuchibshah27"
    password = quote_plus("Lead4earth@123")
    uri = f"mongodb+srv://{username}:{password}@cluster0.vylcw3d.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
    #uri = "mongodb+srv://<username>:<password>@ac-gfjrlzm.mongodb.net/?retryWrites=true&w=majority&tls=true"
    client = MongoClient(uri)
    db = client["meeting_db"]
    meetings_collection = db["meetings"]
    return meetings_collection


def create_calendar_event(creds, meeting_date, meeting_time, city):
    try:
        start_dt = datetime.strptime(f"{meeting_date} {meeting_time}", "%B %d, %Y %I:%M %p")
        end_dt = start_dt + timedelta(hours=1)

        event = {
            'summary': f'City Council Meeting - {city}',
            'location': f'{city}, CA',
            'description': 'Auto-scheduled meeting from Gmail automation',
            'start': {
                'dateTime': start_dt.isoformat(),
                'timeZone': 'America/Los_Angeles',
            },
            'end': {
                'dateTime': end_dt.isoformat(),
                'timeZone': 'America/Los_Angeles',
            },
        }

        logging.info(f"Creating calendar event: {event}")  

        calendar = build('calendar', 'v3', credentials=creds)

        created_event = calendar.events().insert(calendarId='primary', body=event).execute()

        logging.info("Google Calendar event created successfully.")
        logging.info(f"View event: {created_event.get('htmlLink')}")  

    except Exception as e:
        logging.error(f"Calendar event creation failed: {e}")


def trigger_use_case_2(body_text, meetings_collection, creds):
    match = re.search(r"scheduled for ([A-Za-z]+ \d{1,2}, \d{4}) at ([0-9: ]+[APMapm]+)", body_text)
    
    if match:
        meeting_date = match.group(1)
        meeting_time = match.group(2)

        # 🔍 Extract city like "City of Fremont", "City of San Jose"
        city_match = re.search(r"City of ([A-Za-z\s]+)", body_text)
        if city_match:
            city = city_match.group(1).strip()
        else:
            city = "Unknown"

        logging.info(f"Detected next meeting: {meeting_date} at {meeting_time} in {city}")

        # Prevent duplicate
        existing = meetings_collection.find_one({
            "meeting_date": meeting_date,
            "meeting_time": meeting_time,
            "city": city
        })

        if existing:
            logging.info("Meeting already exists in database. Skipping insert.")
        else:
            # ✅ Insert into MongoDB
            meetings_collection.insert_one({
                "meeting_date": meeting_date,
                "meeting_time": meeting_time,
                "city": city,
                "created_at": datetime.utcnow()
            })
            logging.info("Meeting inserted successfully.")

            # ✅ Create calendar event
            create_calendar_event(creds, meeting_date, meeting_time, city)

            # ✅ Send email to volunteers
            subject = f"Meeting Scheduled: {city} - {meeting_date} at {meeting_time}"
            body = f"A new city meeting has been scheduled:\n\nCity: {city}\nDate: {meeting_date}\nTime: {meeting_time}\n\nPlease mark your calendars."
            message = MIMEText(body)
            message['Subject'] = subject
            message['From'] = SENDER_EMAIL
            message['To'] = ", ".join(VOLUNTEERS)

            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(SENDER_EMAIL, APP_PASSWORD)
                server.sendmail(SENDER_EMAIL, VOLUNTEERS, message.as_string())

            logging.info("📧 Notification sent to volunteers about the meeting.")

    else:
        logging.info("Could not detect meeting schedule from body.")



def trigger_use_case_2_old(body_text, conn):
    match = re.search(r"scheduled for ([A-Za-z]+ \d{1,2}, \d{4}) at ([0-9: ]+[APMapm]+)", body_text)
    
    if match:
        meeting_date = match.group(1)
        meeting_time = match.group(2)
        
        logging.info(f"Detected next meeting: {meeting_date} at {meeting_time}")
        
        cursor = conn.cursor()
        cursor.execute("INSERT INTO meetings (meeting_date, meeting_time) VALUES (?, ?)",
                       (meeting_date, meeting_time))
        conn.commit()
    else:
        logging.info("Could not detect meeting schedule from body.")



def send_notification():
    body = "A new city meeting video has been published."
    subject = "New Meeting Video Alert"
    message = MIMEText(body)
    message['Subject'] = subject
    message['From'] = SENDER_EMAIL
    message['To'] = ", ".join(VOLUNTEERS)

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.sendmail(SENDER_EMAIL, VOLUNTEERS, message.as_string())

    logging.info("Notification sent to volunteers.")

def trigger_use_case_1():
    logging.info("Detected: New meeting video published email.")
    send_notification()



def check_and_notify():
    #conn = init_db()
    meetings_collection = init_db()

    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    else:
        flow = InstalledAppFlow.from_client_secrets_file('client_secret_key.json', SCOPES)
        creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    service = build('gmail', 'v1', credentials=creds)

    # Fetch recent emails (last 1 day)
    results = service.users().messages().list(
        userId='me', q="is:unread newer_than:1d", labelIds=['INBOX']).execute()
    messages = results.get('messages', [])

    for msg in messages:
        msg_data = service.users().messages().get(
            userId='me', id=msg['id'], format='full').execute()

        headers = msg_data['payload']['headers']
        subject = sender = None
        for header in headers: 
            if header['name'] == 'Subject':
                subject = header['value']
            if header['name'] == 'From':
                sender = header['value']

        # Extract plain text body
        body = ""
        parts = msg_data['payload'].get('parts', [])
        for part in parts:
            if part['mimeType'] == 'text/plain' and 'data' in part['body']:
                data = part['body']['data']
                body = base64.urlsafe_b64decode(data).decode('utf-8')

        #print(f"\nFrom: {sender}")
        #print(f"Subject: {subject}")
        #print(f"Body (short): {body[:200]}...")

        body_lower = body.lower()
        subject_lower = subject.lower()

        # === Use Case Matching ===
        if "new meeting video" in subject_lower or "video has been published" in body_lower:
            print("Detected: New meeting video published email.")
            trigger_use_case_1()
            service.users().messages().modify(
                userId='me',
                id=msg['id'],
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
        elif "next meeting" in subject_lower or "scheduled for" in body_lower:
            print("Detected: Upcoming meeting schedule email.")
            #trigger_use_case_2(body_lower, conn)
            #trigger_use_case_2(body_lower, meetings_collection)
            trigger_use_case_2(body_lower, meetings_collection, creds)

            service.users().messages().modify(
                userId='me',
                id=msg['id'],
                body={'removeLabelIds': ['UNREAD']}
            ).execute()


        # ✅ Mark email as read so it's not reprocessed
        #service.users().messages().modify(
            #userId='me',
            #id=msg['id'],
            #body={'removeLabelIds': ['UNREAD']}
        #).execute()

if __name__ == '__main__':
    logging.info(" Running a one-time email check...")
    check_and_notify()
