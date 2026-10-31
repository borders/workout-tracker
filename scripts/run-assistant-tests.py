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
        token = secrets.token_urlsafe(48)
        write_private(private/'assistant-token', token)
        with socket.socket() as reservation:
            reservation.bind(('127.0.0.1', 0))
            port = reservation.getsockname()[1]
        env = dict(os.environ, FIELDWORK_CONFIG=str(config), FIELDWORK_PRIVATE_DIR=directory,
                   FIELDWORK_TESTING='1', FIELDWORK_LOGIN_TESTING='1', ASSISTANT_TEST_TOKEN=token,
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
        server = subprocess.Popen([php, '-S', f'127.0.0.1:{port}', str(router)], env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
        finally:
            server.terminate()
            server.wait(timeout=5)
finally:
    admin('DROP DATABASE '+name)
