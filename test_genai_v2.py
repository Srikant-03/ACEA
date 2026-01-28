
from google import genai
import os
from dotenv import load_dotenv

# Load env from backend/.env manually for script
load_dotenv("backend/.env")

api_keys = os.getenv("GEMINI_API_KEYS", "").split(",")
key = api_keys[0].strip()

print(f"Testing with key: ...{key[-4:]}")

client = genai.Client(api_key=key)

print("\n--- Listing Available Models (New SDK) ---")
try:
    # New SDK might have differen list_models method
    # Usually client.models.list()
    # Pagination might be needed, but let's try basic iteration
    
    # Note: The new SDK structure is slightly different.
    # documentation: https://github.com/google-gemini/google-genai-sdk-python
    
    # We will try to list and print names
    pager = client.models.list()
    for model in pager:
        print(f" - {model.name} ({model.display_name})")
        
except Exception as e:
    print(f"Error listing models: {e}")

print("\n--- Testing Generation (gemini-2.0-flash) ---")
try:
    response = client.models.generate_content(
        model="gemini-2.0-flash", 
        contents="Hello, represent the number 42 as a JSON object."
    )
    print(f"Success: {response.text}")
except Exception as e:
    print(f"Error 2.0-flash: {e}")

print("\n--- Testing Generation (gemini-1.5-pro) ---")
try:
    response = client.models.generate_content(
        model="gemini-1.5-pro", 
        contents="Hello"
    )
    print(f"Success: {response.text}")
except Exception as e:
    print(f"Error 1.5-pro: {e}")
