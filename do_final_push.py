import subprocess, os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.chdir('D:\\video-dna')

# Switch to SSH
subprocess.run(['git','remote','set-url','origin','git@github.com:jsjj2598-bit/video-dna.git'], capture_output=True)

# Push both new commits
r = subprocess.run(['git','push','origin','master'], capture_output=True, text=True, errors='replace')
sys.stdout.write('=== PUSH RESULT (rc=' + str(r.returncode) + ') ===\n')
if r.stdout.strip():
    sys.stdout.write(r.stdout + '\n')
if r.stderr.strip():
    sys.stdout.write(r.stderr + '\n')