
try:
    from google import genai
    print("SUCCESS: google.genai imported successfully")
    import os
    from app.core.config import settings
    # Use environment variable or config
    api_key = os.getenv("GEMINI_API_KEY") 
    if not api_key:
        print("WARNING: GEMINI_API_KEY not found in environment")
        return
        
    client = genai.Client(api_key=api_key)
    print("SUCCESS: Client instantiated")
except ImportError as e:
    print(f"ERROR: {e}")
except Exception as e:
    print(f"ERROR: {e}")
