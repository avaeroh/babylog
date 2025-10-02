# scripts/export_openapi.py
import json
from app.main import app

if __name__ == "__main__":
    with open("openapi.json", "w") as f:
        json.dump(app.openapi(), f, indent=2)
    print("Wrote openapi.json")
