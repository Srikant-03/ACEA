import sys
import os

# Ensure backend directory is in path
sys.path.insert(0, os.getcwd())

try:
    print("Importing app.main...")
    from app.main import app
    print("Imported app.main")

    print("Importing TestClient...")
    from fastapi.testclient import TestClient
    print("Imported TestClient")

    print("Initializing TestClient...")
    client = TestClient(app)
    print("Initialized TestClient")

    print("Making request...")
    response = client.get("/health")
    print(f"Response: {response.status_code}")

except Exception as e:
    import traceback
    traceback.print_exc()
