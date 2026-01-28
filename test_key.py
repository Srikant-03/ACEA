import google.generativeai as genai
import os

key = "***REMOVED***"
genai.configure(api_key=key)

print("--- START MODEL LIST ---")
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(m.name)
except Exception as e:
    print(f"ERROR: {e}")
print("--- END MODEL LIST ---")
