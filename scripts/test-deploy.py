"""Exercise the actual deployment shell script against an isolated fake SSH host."""
from pathlib import Path
import os
import subprocess
import tempfile

root = Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix='fieldwork-deploy-') as tmp:
    base = Path(tmp)
    tools = base / 'bin'
    tools.mkdir()
    remote = base / 'remote'
    web = remote / 'borderseng.com'
    web.mkdir(parents=True)
    (web / 'index.html').write_text('existing website')
    (web / '.htaccess').write_text('# existing root configuration')
    ssh = tools / 'ssh'
    ssh.write_text('''#!/usr/bin/env python3
import os, subprocess, sys
args=sys.argv[1:]
if '-O' in args or '-M' in args: sys.exit(0)
i=args.index('jborders@borderseng.com')
command=args[i+1:]
assert len(command)==1
child=os.environ.copy();child['HOME']=child['MOCK_REMOTE_HOME']
sys.exit(subprocess.run(['bash','-c',command[0]],env=child).returncode)
''')
    ssh.chmod(0o755)
    htpasswd = tools / 'htpasswd'
    htpasswd.write_text('''#!/usr/bin/env python3
import sys
from pathlib import Path
# Synthetic noncredential marker, never used by a live web server.
Path(sys.argv[2]).write_text('fieldwork:synthetic-test-marker\\n')
''')
    htpasswd.chmod(0o755)
    php = tools / 'php'
    php.write_text('#!/bin/sh\nexit 0\n')
    php.chmod(0o755)
    environ = dict(os.environ, MOCK_REMOTE_HOME=str(remote), PATH=str(tools)+os.pathsep+os.environ['PATH'])
    script = ['bash', str(root / 'scripts/deploy-dreamhost.sh')]
    def run(): return subprocess.run(script, cwd=root, env=environ, capture_output=True, text=True)
    # Existing content is an explicit blocker and must survive intact.
    target = web / 'workouts'
    target.mkdir()
    (target / 'keep.txt').write_text('user-owned content')
    result = run()
    assert result.returncode != 0, result.stdout
    assert (target / 'keep.txt').read_text() == 'user-owned content'
    assert not (remote / '.fieldwork').exists()
    (target / 'keep.txt').unlink()
    target.rmdir()
    result = run()
    assert result.returncode == 0, result.stderr
    assert target.is_symlink()
    first = target.resolve()
    assert (first / 'index.html').is_file()
    protection = (first / '.htaccess').read_text()
    assert 'SSLRequireSSL' in protection and 'RewriteRule ^ gate.php [END]' in protection
    assert 'AuthType None' in protection and 'DirectoryIndex gate.php' in protection
    result = run()
    assert result.returncode == 0, result.stderr
    assert target.resolve() != first
    assert first.is_dir(), 'Previous release must remain recoverable'
    assert (web / 'index.html').read_text() == 'existing website'
    assert (web / '.htaccess').read_text() == '# existing root configuration'
    print('PASS: deployment refuses unmanaged content, protects staged releases, retains rollback releases, and leaves the existing site unchanged (simulated SSH host)')
