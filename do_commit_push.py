"""Git add/commit/push with file-based logging."""
import subprocess, os, sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

TOKEN = "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"
REPO_URL = f"https://jsjj2598-bit:{TOKEN}@github.com/jsjj2598-bit/video-dna.git"

LOG = open("git_log.txt", "w", encoding="utf-8")

def run(*args, timeout=60):
    r = subprocess.run(args, capture_output=True, text=True, cwd=os.getcwd(), timeout=timeout)
    return r

LOG.write("=== git add ===\n")
run("git", "add", "-A")

LOG.write("=== git commit ===\n")
env = os.environ.copy()
env.update({
    "GIT_AUTHOR_NAME": "video-dna-bot",
    "GIT_AUTHOR_EMAIL": "bot@video-dna.dev",
    "GIT_COMMITTER_NAME": "video-dna-bot",
    "GIT_COMMITTER_EMAIL": "bot@video-dna.dev",
})
r = run("git", "commit", "-m", "AI短剧/漫剧优化: 场景分类+情绪分析+人脸检测+SRT字幕+批量处理+桌面端", env=env)
LOG.write(f"commit: {r.returncode}\n{r.stdout}\n{r.stderr}\n")

LOG.write("=== git remote ===\n")
run("git", "remote", "remove", "origin")
run("git", "remote", "add", "origin", REPO_URL)

LOG.write("=== git push ===\n")
r = run("git", "push", "-u", "origin", "master", timeout=120)
LOG.write(f"push: {r.returncode}\n{r.stdout}\n{r.stderr}\n")

LOG.write("=== DONE ===\n")
LOG.close()

# Print result
with open("git_log.txt", encoding="utf-8") as f:
    print(f.read())