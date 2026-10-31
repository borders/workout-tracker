"""No server or database needed: exercise diagnostics with private temporary files."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

php = os.environ.get('PHP_BINARY') or shutil.which('php')
assert php, 'Set PHP_BINARY to a PHP 8.1+ executable'
helper = Path(__file__).resolve().parent.parent / 'server/api/diagnostics.php'
with tempfile.TemporaryDirectory() as directory:
    env = dict(os.environ, FIELDWORK_DIAGNOSTICS_DIR=directory)
    def command(action):
        return subprocess.run([php,str(helper),action],env=env,capture_output=True,text=True,check=True)
    def record(origin='null',site='same-origin',match=False):
        server={'REQUEST_METHOD':'POST','HTTP_ORIGIN':origin,'HTTP_SEC_FETCH_SITE':site,
                'HTTP_X_FIELDWORK_DISPLAY_MODE':'standalone','HTTP_X_CSRF_TOKEN':'TOKEN_SENTINEL',
                'HTTP_COOKIE':'PASSWORD_SENTINEL','HTTP_AUTHORIZATION':'AUTH_SENTINEL',
                'HTTP_USER_AGENT':'USER_AGENT_SENTINEL','REMOTE_ADDR':'IP_SENTINEL'}
        code="require "+json.dumps(str(helper))+"; $_SERVER=json_decode(stream_get_contents(STDIN),true); $_GET=['action'=>'push']; $_COOKIE=['fieldwork_login'=>'COOKIE_SENTINEL']; syncDiagWrite(403,"+('true' if match else 'false')+");"
        result=subprocess.run([php,'-r',code],input=json.dumps(server),env=env,capture_output=True,text=True,check=True)
        assert not result.stdout and not result.stderr
    log=Path(directory)/'requests.ndjson';flag=Path(directory)/'enabled.json'
    record();assert not log.exists(), 'Must default off'
    command('enable');record()
    entry=json.loads(log.read_text())
    assert entry['origin']=='null' and entry['display_mode']=='standalone'
    assert entry['csrf_matches'] is False and entry['csrf_header_present'] is True
    assert entry['login_cookie_present'] is True and entry['status']==403
    for secret in ['TOKEN_SENTINEL','PASSWORD_SENTINEL','AUTH_SENTINEL','USER_AGENT_SENTINEL','IP_SENTINEL','COOKIE_SENTINEL']:
        assert secret not in log.read_text()
    record('https://user:secret@example.com/path?token=SECRET','SECRET_METADATA')
    last=json.loads(log.read_text().splitlines()[-1]);assert last['origin']=='[invalid/redacted]' and last['sec_fetch_site']=='[other/redacted]'
    record('https://borderseng.com',match=True);assert json.loads(log.read_text().splitlines()[-1])['csrf_matches'] is True
    size=log.stat().st_size
    flag.write_text(json.dumps({'started':int(time.time())-7200,'expires':int(time.time())-3600}));record();assert log.stat().st_size==size
    flag.write_text(json.dumps({'started':int(time.time()),'expires':int(time.time())+86400}));record();assert log.stat().st_size==size
    command('enable');log.write_bytes(b'x'*262144);record();assert log.stat().st_size==262144
    command('disable');assert not flag.exists() and not log.exists()
print('PASS: disabled by default, strict allowlist/redaction, boolean-only credential checks, one-hour expiry, bounded size, and disable/purge')
