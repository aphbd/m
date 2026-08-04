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
    """تعديل الكود المُجلب بأمان - لا نلمس input() داخل strings"""
    lines = code.split('\n')
    new_lines = []
    
    for line in lines:
        original = line
        stripped = line.strip()
        
        # تخطي التعليقات
        if stripped.startswith('#'):
            new_lines.append(original)
            continue
        
        # 🔴 استبدال input() فقط في تعيينات متغيرات (assignments)
        # username = input().strip()  →  username = "auto"
        if re.match(r'^(\s*)(\w+)\s*=\s*input\(\)\.strip\(\)\s*$', stripped):
            var = re.match(r'^(\s*)(\w+)\s*=', stripped).group(2)
            indent = re.match(r'^(\s*)', stripped).group(1)
            new_lines.append(f'{indent}{var} = "auto"')
            continue
        
        # number = int(input().strip())  →  number = 42
        if re.match(r'^(\s*)(\w+)\s*=\s*int\(input\(\)\.strip\(\)\)\s*$', stripped):
            var = re.match(r'^(\s*)(\w+)\s*=', stripped).group(2)
            indent = re.match(r'^(\s*)', stripped).group(1)
            new_lines.append(f'{indent}{var} = 42')
            continue
        
        # أي variable = input(...)  →  variable = ""
        if re.match(r'^(\s*)(\w+)\s*=\s*input\([^)]*\)\s*$', stripped):
            var = re.match(r'^(\s*)(\w+)\s*=', stripped).group(2)
            indent = re.match(r'^(\s*)', stripped).group(1)
            new_lines.append(f'{indent}{var} = ""')
            continue
        
        # تعطيل فحص البيئة الوهمية
        if 'real_prefix' in stripped and stripped.startswith('if'):
            indent = re.match(r'^(\s*)', stripped).group(1)
            new_lines.append(f'{indent}if False:  # disabled venv check')
            continue
        
        if 'Please run this script using the official Termux Python.' in stripped:
            indent = re.match(r'^(\s*)', stripped).group(1)
            new_lines.append(f'{indent}pass  # disabled venv msg')
            continue
        
        if stripped == 'sys.exit(1)':
            indent = re.match(r'^(\s*)', stripped).group(1)
            new_lines.append(f'{indent}pass  # disabled exit')
            continue
        
        # تغيير منفذ Flask إلى 0 (عشوائي)
        if re.search(r'\bport\s*=\s*\d+\b', stripped) and not stripped.startswith('#'):
            original = re.sub(r'\b(port\s*=\s*)\d+\b', r'\g<1>0', original)
        
        new_lines.append(original)
    
    return '\n'.join(new_lines)

def get_clean_python():
    python_path = shutil.which("python3") or shutil.which("python")
    return python_path or sys.executable

def get_clean_env():
    clean_env = os.environ.copy()
    for key in ["VIRTUAL_ENV", "PYTHONHOME", "_OLD_VIRTUAL_PATH", "_OLD_VIRTUAL_PROMPT"]:
        clean_env.pop(key, None)
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

    # 🔴 تشغيل الملف في المجلد الحالي بدلاً من /tmp
    # (يحل مشكلة "بيئة موقتة" إذا كان الكود يحتاج ملفات جانبية)
    with tempfile.NamedTemporaryFile(
        suffix=".py", 
        delete=False, 
        mode="w", 
        encoding='utf-8',
        dir=os.getcwd()  # <-- في نفس المجلد
    ) as tmp:
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
                stdin=subprocess.DEVNULL,  # منع EOFError
                cwd=os.getcwd()  # <-- العمل في المجلد الحالي
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

