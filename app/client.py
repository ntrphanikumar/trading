import os
from dhanhq import dhanhq
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

client_id = os.getenv("client_id")
access_token = os.getenv("access_token")
dhan = dhanhq(client_id, access_token)
