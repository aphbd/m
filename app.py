from flask import Flask, request, Response, stream_with_context, jsonify
import subprocess
import sys
import requests
import tempfile
import os
import re
import shutil
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

LICENSES_URL = os.getenv("L")
TOOL_URL = os.getenv("TO")

if not LICENSES_URL or not TOOL_URL:
    raise ValueError("LICENSES_URL and TOOL_URL must be set in .env file")

def fetch_licenses():
    try:
        r = requests.get(LICENSES_URL, timeout=10)
        r.raise_for_status()
        return [line.strip() for line in r.text.splitlines() if line.strip()]
    except Exception as e:
        print(f" Failed to fetch licenses: {e}")
        return []

def is_licensed(fp):
    return fp in fetch_licenses()

def fetch_tool():
    try:
        r = requests.get(TOOL_URL, timeout=10)
        r.raise_for_status()
        code = r.text
        if re.match(r'^[a-f0-9]{64}$', code.strip()):
            raise Exception("URL contains a fingerprint, not tool code.")
        return code
    except Exception as e:
        print(f" Failed to fetch tool: {e}")
        return 'print(" Default tool (update TOOL_URL)")'

def sanitize_code(code):
    """
    استبدال جميع استدعاءات input() بقيم افتراضية لمنع EOFError.
    """
    # استبدال input() بدون وسيط
    code = re.sub(r'input\s*\(\)', '"default"', code)
    # استبدال input('prompt') بـ "default" أيضًا
    code = re.sub(r'input\s*\([^)]*\)', '"default"', code)
    # معالجة حالات مثل int(input()) -> int("default") -> 0 (لكننا نفضل استخدام 42)
    code = re.sub(r'int\s*\(\s*input\s*\([^)]*\)\s*\)', '42', code)
    code = re.sub(r'float\s*\(\s*input\s*\([^)]*\)\s*\)', '3.14', code)
    # يمكن إضافة المزيد من التحويلات حسب الحاجة
    return code

@app.route("/run", methods=["POST"])
def run_tool():
    data = request.json
    if not data or not data.get("fingerprint"):
        return jsonify({"error": "Invalid data"}), 400

    fp = data["fingerprint"]
    if not is_licensed(fp):
        return jsonify({
            "status": "unauthorized",
            "message": "Device not licensed. Contact the developer."
        }), 403

    tool_code = fetch_tool()
    tool_code = sanitize_code(tool_code)  # تطبيق التعقيم

    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding='utf-8') as tmp:
        tmp.write(tool_code)
        tmp_path = tmp.name

    def generate():
        try:
            # استخدام Python النظامي لتجنب مشاكل البيئة الافتراضية
            if sys.prefix != sys.base_prefix:
                python_path = shutil.which('python3') or '/usr/bin/python3'
            else:
                python_path = sys.executable

            proc = subprocess.Popen(
                [python_path, tmp_path],
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(" License server running...")
    app.run(host="0.0.0.0", port=port)
