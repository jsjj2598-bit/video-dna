"""Create GitHub Release and upload installer."""
import subprocess, os, sys, json, urllib.request

os.chdir(os.path.dirname(os.path.abspath(__file__)))

TOKEN = "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"

REPO = "jsjj2598-bit/video-dna"
TAG = "v0.2.0"
INSTALLER = "dist/Video DNA Analyzer 0.2.0.exe"

if not os.path.exists(INSTALLER):
    print(f"Installer not found: {INSTALLER}")
    sys.exit(1)

def gh_api(method, path, body_data=None):
    url = f"https://api.github.com/repos/{REPO}{path}"
    body = json.dumps(body_data).encode() if body_data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())
    except Exception as e:
        return -1, {"error": str(e)}

# 1. Create release
print("Creating release...")
status, data = gh_api("POST", "/releases", {
    "tag_name": TAG,
    "name": f"Video DNA Analyzer {TAG}",
    "body": "AI短剧/漫剧优化版\n## 新增\n- 镜头类型分类 (dialogue/action/establishing/closeup/emotional/transition)\n- 情绪色调分析 (warm/cool/neutral)\n- 人脸检测 (face_count)\n- SRT字幕导出\n- 批量处理 (--input-dir)\n## 桌面端\n- Electron 原生窗口 + 自动后端启动\n- Windows 便携版 / macOS DMG / Linux AppImage\n",
    "draft": False,
    "prerelease": False,
})
if status == 201:
    release = data
    print(f"  Created: {release['html_url']}")
elif status == 422 and "already_exists" in str(data):
    # Already exists, get existing release
    status, data = gh_api("GET", f"/releases/tags/{TAG}")
    if status == 200:
        release = data
        print(f"  Existing: {release['html_url']}")
    else:
        print(f"  FAILED to get existing release: {data}")
        sys.exit(1)
else:
    print(f"  FAILED ({status}): {data}")
    sys.exit(1)

# 2. Upload installer asset
upload_url = release["upload_url"].replace("{?name,label}", f"?name={os.path.basename(INSTALLER)}")
print("Uploading installer...")
with open(INSTALLER, "rb") as f:
    installer_data = f.read()

req = urllib.request.Request(upload_url, data=installer_data, method="POST")
req.add_header("Authorization", f"Bearer {TOKEN}")
req.add_header("Accept", "application/vnd.github+json")
req.add_header("Content-Type", "application/octet-stream")

try:
    with urllib.request.urlopen(req, timeout=300) as resp:
        asset = json.loads(resp.read().decode())
    print(f"  Uploaded: {asset['browser_download_url']}")
    print(f"\nSUCCESS!")
    print(f"  Release: {release['html_url']}")
    print(f"  Download: {asset['browser_download_url']}")
except urllib.error.HTTPError as e:
    print(f"  FAILED ({e.code}): {e.read().decode()[:200]}")
    sys.exit(1)
except Exception as e:
    print(f"  FAILED: {e}")
    sys.exit(1)