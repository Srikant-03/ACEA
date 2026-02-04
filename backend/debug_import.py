import sys
import os

# Ensure backend directory is in path
sys.path.insert(0, os.getcwd())

try:
    print("Attempting to import app.main...")
    import app.main
    print("Successfully imported app.main")
except Exception as e:
    import traceback
    traceback.print_exc()
