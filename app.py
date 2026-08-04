from flask import Flask, request, Response, stream_with_context, jsonify
import subprocess
import sys
import requests
import tempfile
import os
import re
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# --- الإعدادات من .env ---
LICENSES_URL = os.getenv("L")          # رابط ملف التراخيص
TOOL_URL = os.getenv("TO")            # رابط كود الأداة
ADMIN_PASSWORD = os.getenv("ADMIN_PASS", "admin123")  # كلمة مرور لإضافة ترخيص (غيّرها)
LOG_FILE = os.getenv("LOG_FILE", "access.log")       # ملف السجلات

if not LICENSES_URL or not TOOL_URL:
    raise ValueError("LICENSES_URL (L) and TOOL_URL (TO) must be set in .env file")

# --- سجل المحاولات (في الذاكرة) ---
access_log = []

def log_access(fp, status):
    """تسجيل محاولة الوصول مع الوقت والحالة."""
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fingerprint": fp,
        "status": status
    }
    access_log.append(entry)
    # كتابة في ملف السجل
    try:
        with open(LOG_FILE, "a") as f:
            f.write(f"{entry['timestamp']} | {fp} | {status}\n")
    except Exception:
        pass

# --- جلب قائمة التراخيص ---
def fetch_licenses():
    try:
        r = requests.get(LICENSES_URL, timeout=10)
        r.raise_for_status()
        return [line.strip() for line in r.text.splitlines() if line.strip()]
    except Exception as e:
        print(f"[!] Failed to fetch licenses: {e}")
        return []

# --- التحقق من الترخيص ---
def is_licensed(fp):
    return fp in fetch_licenses()

# --- جلب كود الأداة ---
def fetch_tool():
    try:
        r = requests.get(TOOL_URL, timeout=10)
        r.raise_for_status()
        code = r.text
        # منع تحميل بصمة بدلاً من كود
        if re.match(r'^[a-f0-9]{64}$', code.strip()):
            raise Exception("URL contains a fingerprint, not tool code.")
        return code
    except Exception as e:
        print(f"[!] Failed to fetch tool: {e}")
        return 'print("Default tool - update TOOL_URL")'

# --- نقطة التشغيل الرئيسية (للعميل) ---
@app.route("/run", methods=["POST"])
def run_tool():
    data = request.json
    if not data or not data.get("fingerprint"):
        return jsonify({"error": "Invalid data, fingerprint required"}), 400

    fp = data["fingerprint"]

    if not is_licensed(fp):
        # طباعة المعرف في سجل الخادم (لتتمكن من رؤيته وإضافته)
        print(f"\n{'='*50}")
        print(f"[!] Unauthorized access attempt!")
        print(f"    Device ID: {fp}")
        print(f"{'='*50}\n")
        log_access(fp, "denied")

        # إرجاع المعرف للمستخدم في الرد (لتسهيل النسخ)
        return jsonify({
            "status": "unauthorized",
            "message": "Device not licensed. Send this ID to the developer.",
            "device_id": fp
        }), 403

    # الوصول مصرح به
    log_access(fp, "authorized")
    tool_code = fetch_tool()
    # تعديل المتغيرات الافتراضية (حسب حاجتك)
    tool_code = tool_code.replace('username = input().strip()', 'username = "auto"')
    tool_code = tool_code.replace('number = int(input().strip())', 'number = 42')

    # إنشاء ملف مؤقت لتشغيل الكود
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding='utf-8') as tmp:
        tmp.write(tool_code)
        tmp_path = tmp.name

    def generate():
        try:
            proc = subprocess.Popen(
                [sys.executable, tmp_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            for line in iter(proc.stdout.readline, ''):
                if line:
                    yield line
            proc.wait()
        finally:
            try:
                os.unlink(tmp_path)
            except:
                pass

    return Response(stream_with_context(generate()), mimetype="text/plain")

# --- نقطة إضافة ترخيص جديد (للمطور فقط) ---
@app.route("/license/add", methods=["POST"])
def add_license():
    data = request.json
    if not data or not data.get("fingerprint"):
        return jsonify({"error": "fingerprint required"}), 400
    if data.get("password") != ADMIN_PASSWORD:
        return jsonify({"error": "unauthorized"}), 403

    fp = data["fingerprint"]
    # نحاول إضافته للملف الخارجي (إن كان قابل للكتابة)
    # في هذا المثال: فقط نضيفه إلى ملف محلي، لكن الأفضل أن تحدث المصدر الأصلي.
    try:
        with open("licenses.txt", "a") as f:
            f.write(fp + "\n")
        return jsonify({"status": "added", "device_id": fp})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- نقطة عرض السجلات (اختياري) ---
@app.route("/admin/logs", methods=["GET"])
def view_logs():
    pw = request.args.get("pass")
    if pw != ADMIN_PASSWORD:
        return jsonify({"error": "unauthorized"}), 403
    # عرض آخر 50 سجل
    return jsonify(access_log[-50:])

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"[*] License server running on port {port}")
    app.run(host="0.0.0.0", port=port)
