"""Shared Gemini (Vertex AI) client and helpers."""
import os
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.join(
    os.path.dirname(__file__), os.getenv("google_service_account")
)

llm_client = genai.Client(
    vertexai=True,
    project=os.getenv("google_project_id"),
    location=os.getenv("google_location", "global"),
)

MODEL = "gemini-2.5-flash"


def extract_text(response):
    """Extract text from Gemini response, skipping thought parts."""
    text = ""
    if response.candidates and response.candidates[0].content.parts:
        for part in response.candidates[0].content.parts:
            if not getattr(part, "thought", False) and part.text:
                text += part.text
    return text
