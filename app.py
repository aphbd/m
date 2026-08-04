from flask import Flask, request, jsonify
import requests
import os
import re
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

LICENSES_URL = os.getenv("L")
TOOL_URL = os.getenv("TO")
LOG_FILE = os.getenv("LOG_FILE", "access.log")

if not LICENSES_URL or not TOOL_URL:
    raise ValueError("L and TO env vars required")

def fetch_licenses():
    try:
        r = requests.get(LICENSES_URL, timeout=10)
        r.raise_for_status()
        return [line.strip() for line in r.text.splitlines() if line.strip()]
    except Exception as e:
        print(f"[!] License fetch error: {e}")
        return []

def is_licensed(fp):
    return fp in fetch_licenses()

def fetch_tool_code():
    try:
        r = requests.get(TOOL_URL, timeout=10)
        r.raise_for_status()
        code = r.text
        if re.match(r'^[a-f0-9]{64}$', code.strip()):
            raise Exception("Fingerprint returned, not code")
        return code
    except Exception as e:
        print(f"[!] Tool fetch error: {e}")
        return None

def log_access(fp, status):
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"{datetime.now()} | {fp} | {status}\n")
    except:
        pass

@app.route("/get-tool", methods=["POST"])
def get_tool():
    data = request.json
    if not data or "fingerprint" not in data:
        return jsonify({"error": "fingerprint required"}), 400

    fp = data["fingerprint"]

    if not is_licensed(fp):
        log_access(fp, "denied")
        print(f"\n[!] Unauthorized device: {fp}\n")
        return jsonify({
            "status": "unauthorized",
            "device_id": fp,
            "message": "Device not licensed. Send this ID to developer."
        }), 403

    log_access(fp, "authorized")
    tool_code = fetch_tool_code()
    if tool_code is None:
        return jsonify({"error": "Tool not available"}), 500

    # تعديل بسيط لبعض المدخلات (اختياري)
    tool_code = tool_code.replace('username = input().strip()', 'username = "auto"')
    tool_code = tool_code.replace('number = int(input().strip())', 'number = 42')

    # إرسال الكود الخام (نص)
    return tool_code, 200, {"Content-Type": "text/plain; charset=utf-8"}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"[*] License server on port {port}")
    app.run(host="0.0.0.0", port=port)
