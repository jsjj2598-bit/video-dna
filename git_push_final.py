"""Git commit and push all optimized code."""
import subprocess, os, sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

f = open("git_out.txt", "w", encoding="utf-8")

# add
subprocess.run(["git", "add", "-A"], cwd=os.getcwd())
f.write("add done\n")

# commit
env = os.environ.copy()
env.update({"GIT_AUTHOR_NAME":"bot","GIT_AUTHOR_EMAIL":"b@d.com",
            "GIT_COMMITTER_NAME":"bot","GIT_COMMITTER_EMAIL":"b@d.com"})
r = subprocess.run(["git","commit","-m","AI短剧漫剧优化:场景分类+情绪分析+人脸检测+SRT字幕+批量处理+桌面端"],
                   capture_output=True,text=True,cwd=os.getcwd(),env=env,timeout=30)
f.write(f"commit {r.returncode}\n{r.stdout}\n{r.stderr}\n")

# remote
t = "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"
u = f"https://jsjj2598-bit:{t}@github.com/jsjj2598-bit/video-dna.git"
subprocess.run(["git","remote","remove","origin"],cwd=os.getcwd())
subprocess.run(["git","remote","add","origin",u],cwd=os.getcwd())
f.write("remote done\n")

# push
r = subprocess.run(["git","push","-u","origin","master"],
                   capture_output=True,text=True,cwd=os.getcwd(),timeout=120)
f.write(f"push {r.returncode}\n{r.stdout}\n{r.stderr}\n")
f.write("=== DONE ===\n")
f.close()

with open("git_out.txt", encoding="utf-8") as g:
    print(g.read())