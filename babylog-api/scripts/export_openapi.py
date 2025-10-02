# scripts/export_openapi.py
import json
from app.main import app

if __name__ == "__main__":
    with open("openapi.json", "w") as f:
        json.dump(app.specs.openapi(), f, indent=2)
    print("Wrote openapi.json")
