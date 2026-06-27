import json
import os

SETTINGS_FILE = "settings.json"
CREDS_FILE = ".creds"
CACHE_FILE = ".moodle_cache.json"

def sanitize(name: str) -> str:
    for c in '<>:"/\\|?*':
        name = name.replace(c, "_")
    return name.replace("\n", " ").strip()

def load_json(filepath: str) -> dict:
    if os.path.exists(filepath):
        try:
            with open(filepath, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return None

def save_json(filepath: str, data: dict):
    with open(filepath, "w") as f:
        json.dump(data, f, indent=4)
