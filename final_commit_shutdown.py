import subprocess, os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
os.chdir('D:\\video-dna')

# Stage and commit
subprocess.run(['git', 'add', '-A', '.'], check=True)
r = subprocess.run(['git', 'commit', '-m', 'feat: DSH-style sidebar layout + settings/history tabs'], capture_output=True, text=True, errors='replace')
print('commit:', r.stdout or r.stderr)

# Push with timeout
try:
    r2 = subprocess.run(['git', 'push', 'origin', 'master'], capture_output=True, text=True, errors='replace', timeout=30)
    print('push rc:', r2.returncode)
except subprocess.TimeoutExpired:
    print('push timed out (network blocked)')
except Exception as e:
    print('push failed:', e)

# Shutdown
print('Shutting down...')
subprocess.run(['shutdown', '/s', '/t', '0'])