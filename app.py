from flask import Flask, request, Response, stream_with_context, jsonify
import subprocess, sys, requests, tempfile, os, re
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
    tool_code = tool_code.replace('username = input().strip()', 'username = "auto"'
                                  ).replace('number = int(input().strip())', 'number = 42')

    with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w", encoding='utf-8') as tmp:
        tmp.write(tool_code)
        tmp_path = tmp.name

    def generate():
        try:
            proc = subprocess.Popen([sys.executable, tmp_path],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, bufsize=1)
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
    print("License server running...")
    app.run(host="0.0.0.0", port=5000, debug=False)
