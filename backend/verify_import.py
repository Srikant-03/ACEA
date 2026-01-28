
try:
    from google import genai
    print("SUCCESS: google.genai imported successfully")
    client = genai.Client(api_key="test")
    print("SUCCESS: Client instantiated")
except ImportError as e:
    print(f"ERROR: {e}")
except Exception as e:
    print(f"ERROR: {e}")
