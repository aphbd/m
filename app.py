from flask import Flask, request, jsonify
import requests, os, re
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

LICENSES_URL = os.getenv("L")
TOOL_URL = os.getenv("TO")

if not LICENSES_URL or not TOOL_URL:
    raise ValueError("L and TO must be set in .env")

def fetch_licenses():
    try:
        r = requests.get(LICENSES_URL, timeout=10)
        r.raise_for_status()
        return [line.strip() for line in r.text.splitlines() if line.strip()]
    except Exception as e:
        print(f"❌ Failed to fetch licenses: {e}")
        return []

def is_licensed(fp):
    return fp in fetch_licenses()

def fetch_tool_code():
    try:
        r = requests.get(TOOL_URL, timeout=10)
        r.raise_for_status()
        code = r.text
        if re.match(r'^[a-f0-9]{64}$', code.strip()):
            raise Exception("URL contains a fingerprint, not tool code.")
        return code
    except Exception as e:
        print(f"❌ Failed to fetch tool: {e}")
        return 'print("⚠️ Tool not available")'

@app.route("/run", methods=["POST"])
def run_tool():
    data = request.json
    if not data or not data.get("fingerprint"):
        return jsonify({"error": "Invalid data"}), 400

    fp = data["fingerprint"]
    device_info = data.get("device_info", {})

    print(f"[INFO] Fingerprint: {fp}")
    if device_info:
        print("[INFO] Device info:")
        for k, v in device_info.items():
            print(f"    {k}: {v}")

    if not is_licensed(fp):
        print(f"[WARN] Unauthorized: {fp}")
        return jsonify({
            "status": "unauthorized",
            "message": "Device not licensed.",
            "fingerprint": fp,
            "device_info": device_info
        }), 403

    tool_code = fetch_tool_code()
    
    # تحضير البيئة لحل مشاكل التنسيق
    tool_code = (
        "import sys, os\n"
        "try:\n"
        "    import colorama\n"
        "    colorama.init()\n"
        "except ImportError:\n"
        "    pass\n"
        "try:\n"
        "    sys.stdout.reconfigure(line_buffering=True)\n"
        "except:\n"
        "    pass\n"
        "C = None\n"
    ) + tool_code
    
    # تعديل المدخلات
    tool_code = tool_code.replace('username = input().strip()', 'username = "auto"')
    tool_code = tool_code.replace('number = int(input().strip())', 'number = 42')
    
    # إضافة تعريفات إضافية للمتغيرات الشائعة
    tool_code = tool_code.replace('C = None\n', 'C = None\nF = None\nB = None\n')

    return tool_code, 200, {'Content-Type': 'text/plain'}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("✅ License server running (code delivery mode)...")
    app.run(host="0.0.0.0", port=port)
