import os
import json
import time
import threading
from datetime import datetime, timedelta
from flask import Flask, jsonify
import requests

# ========== CONFIG FROM ENVIRONMENT ==========
TARGET_USER = os.environ.get("TARGET_USER")
if not TARGET_USER:
    raise ValueError("TARGET_USER environment variable not set")

TARGET_ID = os.environ.get("TARGET_ID", "46014368707")
FOLLOW_ADET = int(os.environ.get("FOLLOW_ADET", "200"))

# Interval in seconds
KEEPALIVE_INTERVAL = 600      # 10 minutes
FOLLOW_INTERVAL = 4800         # 80 minutes

# ========== SITE DEFINITIONS ==========
# Each site must have:
#   - name: used for env var name and logging
#   - cookie_env: name of env var containing JSON cookie dict
#   - headers: base headers for requests
#   - keepalive_url: (optional) URL for keep‑alive GET
#   - follow_url: (optional) URL for follow POST
#   - follow_data_template: template for POST data (adet, userID, userName filled later)

BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:148.0) Gecko/20100101 Firefox/148.0",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
}

SITES = [
    {
        "name": "takipcimx",
        "cookie_env": "COOKIE_TAKIPCIMX",
        "headers": {**BASE_HEADERS, "Referer": "https://takipcimx.net/tools/send-follower/46014368707"},
        "keepalive_url": "https://takipcimx.net/ajax/keep-session",
        "follow_url": None,
    },
    {
        "name": "takipcizen",
        "cookie_env": "COOKIE_TAKIPCIZEN",
        "headers": {
            **BASE_HEADERS,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://takipcizen.com",
            "Referer": "https://takipcizen.com/tools/send-follower/46014368707",
        },
        "keepalive_url": None,  # No keep‑alive for this site
        "follow_url": "https://takipcizen.com/tools/send-follower/46014368707?formType=send",
    },
    {
        "name": "takipcigen",
        "cookie_env": "COOKIE_TAKIPCI_GEN",
        "headers": {
            **BASE_HEADERS,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://takipcigen.com",
            "Referer": "https://takipcigen.com/tools/send-follower/46014368707",
        },
        "keepalive_url": "https://takipcigen.com/ajax/keep-session",
        "follow_url": "https://takipcigen.com/tools/send-follower/46014368707?formType=send",
    },
    {
        "name": "takipcikrali",
        "cookie_env": "COOKIE_TAKIPCI_KRALI",
        "headers": {
            **BASE_HEADERS,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": "https://takipcikrali.com",
            "Referer": "https://takipcikrali.com/tools/send-follower/46014368707",
        },
        "keepalive_url": "https://takipcikrali.com/ajax/keep-session",
        "follow_url": "https://takipcikrali.com/tools/send-follower/46014368707?formType=send",
    },
]

# ========== SESSION MANAGER ==========
class SiteSession:
    def __init__(self, config):
        self.name = config["name"]
        self.headers = config["headers"]
        self.keepalive_url = config.get("keepalive_url")
        self.follow_url = config.get("follow_url")
        self.session = requests.Session()
        self.session.headers.update(self.headers)

        # Load initial cookies from environment
        cookie_json = os.environ.get(config["cookie_env"])
        if cookie_json:
            try:
                cookies = json.loads(cookie_json)
                self.session.cookies.update(cookies)
                print(f"[{self.name}] Loaded cookies from env")
            except Exception as e:
                print(f"[{self.name}] Failed to parse cookies: {e}")
        else:
            print(f"[{self.name}] No cookies in env, skipping")

        self.last_keepalive = None
        self.last_follow = None

    def do_keepalive(self):
        if not self.keepalive_url:
            return False
        try:
            resp = self.session.get(self.keepalive_url, timeout=30)
            if resp.status_code == 200:
                print(f"[{self.name}] Keep‑alive OK – {resp.text[:50]}")
                self.last_keepalive = datetime.now()
                return True
            else:
                print(f"[{self.name}] Keep‑alive failed: HTTP {resp.status_code}")
                return False
        except Exception as e:
            print(f"[{self.name}] Keep‑alive error: {e}")
            return False

    def do_follow(self):
        if not self.follow_url:
            return False
        data = {
            "adet": str(FOLLOW_ADET),
            "userID": TARGET_ID,
            "userName": TARGET_USER,
        }
        try:
            resp = self.session.post(self.follow_url, data=data, timeout=30)
            if resp.status_code == 200:
                print(f"[{self.name}] Follow OK – {resp.text[:50]}")
                self.last_follow = datetime.now()
                return True
            else:
                print(f"[{self.name}] Follow failed: HTTP {resp.status_code} – {resp.text[:100]}")
                return False
        except Exception as e:
            print(f"[{self.name}] Follow error: {e}")
            return False

# ========== BACKGROUND SCHEDULER ==========
sites = [SiteSession(cfg) for cfg in SITES if os.environ.get(cfg["cookie_env"])]
print(f"Loaded {len(sites)} sites with cookies.")

def scheduler_loop():
    while True:
        now = datetime.now()
        for site in sites:
            # Keep‑alive
            if site.keepalive_url:
                if site.last_keepalive is None or (now - site.last_keepalive).total_seconds() >= KEEPALIVE_INTERVAL:
                    site.do_keepalive()

            # Follow
            if site.follow_url:
                if site.last_follow is None or (now - site.last_follow).total_seconds() >= FOLLOW_INTERVAL:
                    site.do_follow()

        time.sleep(30)  # Check every 30 seconds

# Start scheduler in background thread
thread = threading.Thread(target=scheduler_loop, daemon=True)
thread.start()

# ========== FLASK WEB SERVER (for Render) ==========
app = Flask(__name__)

@app.route('/')
def index():
    return "Takipci automation is running. Check logs for details."

@app.route('/health')
def health():
    return jsonify({"status": "alive", "sites": len(sites)})

# Only for local testing
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
