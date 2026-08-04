from flask import Flask, request, Response, stream_with_context, jsonify
import subprocess, sys, requests, tempfile, os, re, shutil
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

def patch_tool_code(code):
    """تعطيل input() وبيئة وهمية وتغيير منفذ الخادم"""
    
    # 1. استبدال input() المعروف
    code = code.replace('username = input().strip()', 'username = "auto"')
    code = code.replace('number = int(input().strip())', 'number = 42')
    
    # 2. استبدال أي input() آخر بقيمة فارغة
    code = re.sub(r'input\([^)]*\)', '""', code)
    code = re.sub(r'input\(\)', '""', code)
    
    # 3. تعطيل فحص البيئة الوهمية
    code = code.replace(
        'print("Please run this script using the official Termux Python.")',
        'pass  # disabled venv check'
    )
    code = code.replace('sys.exit(1)', 'pass  # disabled exit')
    
    # 4. 🔴 تغيير منفذ Flask/خادم إلى 0 (منفذ عشوائي متاح)
    # استبدال أي تعريف منفذ ثابت
    code = re.sub(r'port\s*=\s*int\(\s*os\.environ\.get\(["\']PORT["\']\s*,\s*\d+\s*\)\s*\)', 
                  'port = 0', code)
    code = re.sub(r'port\s*=\s*int\(\s*os\.environ\.get\(["\']PORT["\']\s*,\s*["\']\d+["\']\s*\)\s*\)', 
                  'port = 0', code)
    code = re.sub(r'port\s*=\s*\d+', 'port = 0', code)
    
    # 5. تعطيل app.run() إذا كان الكود لا يحتاج خادم (اختياري)
    # code = code.replace('app.run(', '# app.run(')
    
    return code

def get_clean_python():
    python_path = shutil.which("python3") or shutil.which("python")
    return python_path or sys.executable

def get_clean_env():
    clean_env = os.environ.copy()
    for key in ["VIRTUAL_ENV", "PYTHONHOME", "_OLD_VIRTUAL_PATH", "_OLD_VIRTUAL_PROMPT"]:
        clean_env.pop(key, None)
    # 🔴 إجبار المنفذ على 0 في البيئة أيضاً
    clean_env['PORT'] = '0'
    return clean_env

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
    tool_code = patch_tool_code(tool_code)

    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding='utf-8') as tmp:
        tmp.write(tool_code)
        tmp_path = tmp.name

    def generate():
        try:
            python_path = get_clean_python()
            clean_env = get_clean_env()
            
            proc = subprocess.Popen(
                [python_path, tmp_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=clean_env,
                stdin=subprocess.DEVNULL
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
