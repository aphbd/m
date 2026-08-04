from flask import Flask, request, Response, jsonify
import sys
import requests
import os
import re
import io
from contextlib import redirect_stdout
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
        print(f"❌ Failed to fetch licenses: {e}")
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
        print(f"❌ Failed to fetch tool: {e}")
        return 'print("⚠️ Default tool (update TOOL_URL)")'

def sanitize_code(code):
    """استبدال input() بقيم افتراضية لتجنب EOFError"""
    code = re.sub(r'input\s*\([^)]*\)', '"default"', code)
    code = re.sub(r'int\s*\(\s*input\s*\([^)]*\)\s*\)', '42', code)
    code = re.sub(r'float\s*\(\s*input\s*\([^)]*\)\s*\)', '3.14', code)
    return code

def validate_and_execute(code):
    """التحقق من صحة الكود نحويًا ثم تنفيذه، وإرجاع المخرجات أو الخطأ."""
    # تعقيم الكود
    code = sanitize_code(code)

    # محاولة التحقق من النحو باستخدام compile
    try:
        compiled = compile(code, '<string>', 'exec')
    except SyntaxError as e:
        # خطأ نحوي، نعيد رسالة واضحة مع رقم السطر
        return f"❌ Syntax error in tool code at line {e.lineno}: {e.msg}\n{e.text}"

    # تنفيذ الكود بعد التحقق
    try:
        f = io.StringIO()
        with redirect_stdout(f):
            # بيئة فارغة للتنفيذ (آمن نسبياً)
            exec(compiled, {})
        output = f.getvalue()
        return output if output else "✅ Tool executed successfully (no output)."
    except Exception as e:
        return f"❌ Runtime error: {str(e)}"

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
    result = validate_and_execute(tool_code)

    return Response(result, mimetype="text/plain")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("🚀 License server running...")
    app.run(host="0.0.0.0", port=port)
