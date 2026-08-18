"""Git add/commit/push all optimized code to GitHub."""
import subprocess, os, sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

TOKEN = "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"
REPO_URL = f"https://jsjj2598-bit:{TOKEN}@github.com/jsjj2598-bit/video-dna.git"

def run(*args, **kwargs):
    r = subprocess.run(args, capture_output=True, text=True, cwd=os.getcwd(), **kwargs)
    if r.stdout.strip():
        print(r.stdout.strip()[-500:])
    if r.stderr.strip():
        err = r.stderr.strip()[-500:]
        if "warning" not in err.lower() and "lf will be replaced" not in err.lower():
            print("ERR:", err)
    return r

# 1. Add all changed files
print("=== git add ===")
run("git", "add", "-A")

# 2. Commit
print("\n=== git commit ===")
run("git", "commit", "-m", 
    "AI短剧/漫剧优化 + SRT导出 + 批量处理 + 情绪分析 + 人脸检测",
    env={**os.environ, "GIT_AUTHOR_NAME": "video-dna-bot", 
         "GIT_AUTHOR_EMAIL": "bot@video-dna.dev",
         "GIT_COMMITTER_NAME": "video-dna-bot",
         "GIT_COMMITTER_EMAIL": "bot@video-dna.dev"})

# 3. Ensure remote
run("git", "remote", "remove", "origin")
run("git", "remote", "add", "origin", REPO_URL)

# 4. Push
print("\n=== git push ===")
r = run("git", "push", "-u", "origin", "master", timeout=60)
if r.returncode != 0:
    print("\nPush failed. Trying with force...")
    r = run("git", "push", "-u", "origin", "master", "--force", timeout=60)

if r.returncode == 0:
    print("\nSUCCESS! Code pushed to GitHub.")
    print(f"   https://github.com/jsjj2598-bit/video-dna")
else:
    print(f"\nFAILED (exit {r.returncode})")
    print("Network may be blocked. Manual push:")
    print("   cd D:\\video-dna")
    print("   git remote add origin https://github.com/jsjj2598-bit/video-dna.git")
    print("   git push -u origin master")