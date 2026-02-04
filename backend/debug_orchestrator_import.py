import sys
import os

sys.path.insert(0, os.getcwd())

try:
    print("Attempting to import app.orchestrator...")
    import app.orchestrator
    print("Success!")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
