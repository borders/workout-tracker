"""Private setup/preflight regression. No network, database or real credentials."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[2]
php=os.environ.get('PHP_BINARY') or shutil.which('php')
assert php
with tempfile.TemporaryDirectory(prefix='mcp-setup-test-') as directory:
    private=Path(directory)
    env=dict(os.environ,FIELDWORK_PRIVATE_DIR=directory)
    script=[php,str(root/'scripts/mcp/setup.php')]
    def setup(issuer='https://tenant.example/',owner='auth0|fixture-owner',confirm='enable'):
        return subprocess.run(script,input='\n'.join([issuer,owner,confirm])+'\n',text=True,capture_output=True,env=env)
    result=setup()
    assert result.returncode==0
    path=private/'mcp-config.json';before=path.read_bytes()
    assert path.stat().st_mode&0o777==0o600
    config=json.loads(before)
    assert config=={'enabled':True,'resource':'https://borderseng.com/workouts/mcp','issuer':'https://tenant.example/','owner_subject':'auth0|fixture-owner'}
    assert setup().returncode!=0 and path.read_bytes()==before,'Setup must not overwrite'
    token=private/'assistant-client-token.txt';token.write_text('x'*64+'\n');token.chmod(0o600)
    check=[php,str(root/'dist/mcp/check.php')]
    result=subprocess.run(check,capture_output=True,env=env)
    assert result.returncode==0 and b'x'*64 not in result.stdout+result.stderr
    token.chmod(0o644)
    assert subprocess.run(check,capture_output=True,env=env).returncode!=0
    token.chmod(0o600)
    path.chmod(0o644)
    assert subprocess.run(check,capture_output=True,env=env).returncode!=0
    path.unlink()
    assert setup(issuer='http://tenant.example/').returncode!=0 and not path.exists()
    assert setup(owner='').returncode!=0 and not path.exists()
    assert setup(confirm='cancel').returncode!=0 and not path.exists()
    # CLI cannot activate loopback/HTTP test exemptions intended for cli-server.
    env['FIELDWORK_MCP_TESTING']='1'
    assert setup(issuer='http://127.0.0.1/').returncode!=0
    path.symlink_to(token)
    assert setup().returncode!=0 and path.is_symlink()
    assert subprocess.run(check,capture_output=True,env=env).returncode!=0
    path.unlink()
    assert subprocess.run(check,capture_output=True,env=env).returncode==0,'Missing config is disabled'
print('PASS: MCP interactive setup/preflight, private modes, no overwrite, invalid input/cancellation/symlink rejection, disabled defaults, and no CLI test bypass (no network/database)')
