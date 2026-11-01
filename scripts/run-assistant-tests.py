"""Create an isolated local DB/token/server, run assistant tests, then clean up."""
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time

root = Path(__file__).resolve().parent.parent
php = os.environ.get('PHP_BINARY') or shutil.which('php')
assert php, 'Set PHP_BINARY to a PHP 8.1+ executable'
config_path = os.environ.get('FIELDWORK_ASSISTANT_TEST_CONFIG')
assert config_path, 'Provide a local disposable MySQL admin config via FIELDWORK_ASSISTANT_TEST_CONFIG'
template = json.loads(Path(config_path).read_text())
assert template['host'] in ('localhost', '127.0.0.1'), 'Refusing non-local database configuration'
name = 'fw_assistant_test_' + secrets.token_hex(8)
bootstrap = 'require ' + json.dumps(str(root/'server/api/lib.php')) + '; $db=connect(configuration()); '
def admin(sql):
    subprocess.run([php, '-r', bootstrap+'$db->exec('+json.dumps(sql)+');'],
                   env=dict(os.environ, FIELDWORK_CONFIG=config_path), capture_output=True, check=True)

subprocess.run([php,str(root/'scripts/assistant/test-security.php')],check=True)
admin('CREATE DATABASE '+name+' CHARACTER SET utf8mb4 COLLATE utf8mb4_bin')
try:
    with tempfile.TemporaryDirectory(prefix='assistant-test-') as directory:
        private = Path(directory)
        def write_private(path, value):
            fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as file:
                file.write(value)
        config = private/'config.json'
        write_private(config, json.dumps({**template, 'database':name}))
        token_path=private/'issued-token'
        token_env=dict(os.environ, FIELDWORK_PRIVATE_DIR=directory)
        subprocess.run([php,str(root/'scripts/assistant/token.php'),'provision',str(token_path)],env=token_env,check=True,capture_output=True)
        token=token_path.read_text().strip()
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        env = dict(os.environ, FIELDWORK_CONFIG=str(config), FIELDWORK_PRIVATE_DIR=directory,
                   FIELDWORK_TESTING='1', FIELDWORK_LOGIN_TESTING='1', ASSISTANT_TEST_TOKEN=token,
                   PHP_BINARY=php, ASSISTANT_TEST_PRIVATE=directory,
                   ASSISTANT_TEST_ROOT=f'http://127.0.0.1:{port}/workouts/api')
        subprocess.run([php, '-r', bootstrap+'migrate($db);'], env=env, check=True, capture_output=True)
        router = private/'router.php'
        write_private(router, '''<?php
$path=parse_url($_SERVER['REQUEST_URI'],PHP_URL_PATH);
if(!in_array($path,['/workouts/api/assistant.php','/workouts/api/sync.php'],true)){http_response_code(404);exit;}
$_SERVER['SCRIPT_NAME']=$path;
if(basename($path)==='assistant.php'){require ''' + json.dumps(str(root/'server/gate.php')) + ''';exit;}
require ''' + json.dumps(str(root/'server/api')) + '''.'/'.basename($path);
''')
        server_log=os.fdopen(os.open(private/'server.log',os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600),'w+b')
        server = subprocess.Popen([php, '-S', f'127.0.0.1:{port}', str(router)], env=env,
                                  stdout=subprocess.DEVNULL, stderr=server_log)
        try:
            for _ in range(100):
                if server.poll() is not None:
                    raise RuntimeError('Local PHP test server exited')
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=.1):
                        break
                except OSError:
                    time.sleep(.05)
            else:
                raise RuntimeError('Local PHP server did not become ready')
            subprocess.run([sys.executable, str(root/'scripts/test-assistant-api.py')], env=env, check=True)
            subprocess.run([sys.executable, str(root/'scripts/test-api.py')], env=dict(env,SYNC_TEST_URL=env['ASSISTANT_TEST_ROOT']+'/sync.php'),check=True)
            subprocess.run([sys.executable, str(root/'scripts/test-assistant-hardening.py')], env=env,check=True)
            server_log.flush();server_log.seek(0)
            logs=server_log.read()
            # Query strings are hosting access-log territory (never send a real
            # credential in a URL); test application failures for private leaks.
            for marker in (b'secret-private-marker',b'private-workout-notes-marker',b'Bearer '+token.encode()):
                assert marker not in logs,'Application failure leaked private material to PHP logs'
            print('PASS: injected SQL errors and private request content are absent from PHP server logs')
            # Browser form-login/CSRF/offline regression uses this same disposable
            # DB, but a separate gate-only listener (no test auth bypass route).
            write_private(private/'htpasswd', subprocess.check_output([php,'-r',"echo 'fieldwork:'.password_hash('local-fixture-only',PASSWORD_BCRYPT);"],env=env).decode())
            gate_router=private/'gate-router.php'
            write_private(gate_router,'<?php require '+json.dumps(str(root/'dist/gate.php'))+';')
            with socket.socket() as reservation:
                reservation.bind(('127.0.0.1',0));gate_port=reservation.getsockname()[1]
            gate=subprocess.Popen([php,'-S',f'127.0.0.1:{gate_port}',str(gate_router)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                for _ in range(100):
                    try:
                        with socket.create_connection(('127.0.0.1',gate_port),timeout=.1):break
                    except OSError:time.sleep(.05)
                subprocess.run(['node',str(root/'scripts/login-smoke.cjs')],env=dict(env,LOGIN_TEST_URL=f'http://127.0.0.1:{gate_port}/workouts/'),check=True,cwd=root)
            finally:
                gate.terminate();gate.wait(timeout=5)


        finally:
            server.terminate()
            server.wait(timeout=5)
            server_log.close()
finally:
    admin('DROP DATABASE '+name)
