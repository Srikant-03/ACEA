import google.generativeai as genai
import os

key = "***REMOVED***"
genai.configure(api_key=key)

models = ["gemini-2.0-flash", "models/gemini-2.0-flash", "gemini-1.5-flash"]

print(f"Using Key: {key[:10]}...")

for m in models:
    print(f"\n--- Testing {m} ---")
    try:
        model = genai.GenerativeModel(m)
        response = model.generate_content("Hello")
        print(f"SUCCESS! Response: {response.text}")
    except Exception as e:
        print(f"FAILED: {e}")
