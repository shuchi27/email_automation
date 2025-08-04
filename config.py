from dotenv import load_dotenv
import os

load_dotenv()

VOLUNTEERS = os.getenv("VOLUNTEERS").split(",")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
APP_PASSWORD = os.getenv("APP_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/gmail.send'
]
