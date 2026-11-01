"""Real Apache rewrite/CGI forwarding regression; synthetic token, no database.

APACHE_BINARY, APACHE_MODULE_DIR and PHP_CGI_BINARY select local Apache 2.4
and PHP CGI. Run after build:hosted. All listeners/files are disposable/local.
"""
import os
from pathlib import Path
import runpy
import shutil
import shlex
import socket
import subprocess
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

root=Path(__file__).resolve().parent.parent
apache=os.environ.get('APACHE_BINARY') or shutil.which('apache2') or shutil.which('httpd')
cgi=os.environ.get('PHP_CGI_BINARY') or shutil.which('php-cgi')
php=os.environ.get('PHP_BINARY') or shutil.which('php')
modules=Path(os.environ.get('APACHE_MODULE_DIR','/usr/lib/apache2/modules'))
assert apache and cgi and php,'Provide Apache, PHP CLI and PHP CGI executables'
# Exercise the actual deployer's rendered heredoc, through the existing fake SSH
# host. This never invokes a real SSH connection or reads any real credentials.
protection=runpy.run_path(str(root/'scripts/test-deploy.py'))['protection']
with tempfile.TemporaryDirectory(prefix='assistant-forwarding-') as temporary:
    base=Path(temporary)
    site=base/'site';site.mkdir()
    shutil.copytree(root/'dist',site/'workouts')
    private=base/'private';private.mkdir(mode=0o700)
    env=dict(os.environ,FIELDWORK_PRIVATE_DIR=str(private))
    output=private/'issued-token'
    subprocess.run([php,str(root/'scripts/assistant/token.php'),'provision',str(output)],env=env,check=True,capture_output=True)
    token=output.read_text().strip()
    wrapper=base/'php-cgi'
    # Fixture-only CGI handler can emulate the other common server-variable
    # shapes without ever accepting them from client headers in production.
    wrapper.write_text('''#!/bin/sh
case "$QUERY_STRING" in
 *forwarding_case=empty-primary*) export HTTP_AUTHORIZATION='' ;;
 *forwarding_case=invalid-primary*) export HTTP_AUTHORIZATION='Bearer invalid' ;;
 *forwarding_case=single-redirect*)
   export HTTP_AUTHORIZATION=''
   export REDIRECT_HTTP_AUTHORIZATION="$REDIRECT_REDIRECT_HTTP_AUTHORIZATION"
   unset REDIRECT_REDIRECT_HTTP_AUTHORIZATION ;;
 *forwarding_case=direct*)
   export HTTP_AUTHORIZATION="$REDIRECT_REDIRECT_HTTP_AUTHORIZATION"
   unset REDIRECT_HTTP_AUTHORIZATION REDIRECT_REDIRECT_HTTP_AUTHORIZATION ;;
esac
exec '''+shlex.quote(cgi)+' -n -d cgi.force_redirect=0 "$@"\n')
    wrapper.chmod(0o700)
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
    # Transport-only fixture: loopback HTTP emulates the HTTPS flag supplied by
    # a TLS terminator. The deployed SSLRequireSSL directive remains asserted by
    # test-deploy.py; only this local fixture removes it. No production secrets.
    htaccess=site/'workouts/.htaccess'
    rendered=protection.replace('SSLRequireSSL\n','')
    htaccess.write_text(rendered)
    config=base/'httpd.conf'
    loaded=['mpm_prefork','authn_core','authz_core','authz_host','dir','mime','env','setenvif','rewrite','cgi','actions','alias','headers']
    config.write_text('\n'.join([
        f'ServerRoot "{base}"',f'PidFile "{base}/httpd.pid"',
        f'Listen 127.0.0.1:{port}',f'ServerName 127.0.0.1:{port}',
        *[f'LoadModule {m}_module "{modules}/mod_{m}.so"' for m in loaded],
        f'ErrorLog "{base}/error.log"','LogLevel warn',
        f'DocumentRoot "{site}"','TypesConfig /dev/null',
        f'<Directory "{base}">','Options +ExecCGI +FollowSymLinks','AllowOverride All','Require all granted','</Directory>',
        f'ScriptAlias /php-handler "{wrapper}"',
        'AddHandler fieldwork-php .php','Action fieldwork-php /php-handler',
        f'SetEnv FIELDWORK_PRIVATE_DIR "{private}"','SetEnv HTTPS on',
    ])+'\n')
    server=subprocess.Popen([apache,'-f',str(config),'-DFOREGROUND'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,start_new_session=True)
    endpoint=f'http://127.0.0.1:{port}/workouts/api/assistant.php?action=forwarding_probe'
    def request(path=endpoint,authorization=None,**headers):
        if authorization is not None:headers['Authorization']=authorization
        try:
            with urlopen(Request(path,headers=headers),timeout=5) as response:
                return response.status,response.read()
        except HTTPError as error:return error.code,error.read()
    try:
        for _ in range(100):
            if server.poll() is not None:raise RuntimeError('Local Apache startup failure: '+server.stderr.read().decode())
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.1):break
            except OSError:time.sleep(.05)
        else:raise RuntimeError('Local Apache did not become ready')
        initial,_=request()
        assert initial==401,f'Anonymous request must stay denied: HTTP {initial}'
        # Unknown action is reached only AFTER successful authentication. This
        # verifies the real gate/API without opening a DB or exposing a token.
        status,_=request(authorization='Bearer '+token)
        assert status==404,f'Valid credential lost during Apache rewrite/CGI: HTTP {status}'
        assert request(authorization='Bearer '+'0'*64)[0]==401
        assert request(authorization='Basic '+token)[0]==401
        assert request(Cookie='fieldwork_login=not-a-real-session')[0]==401
        assert request(**{'X-HTTP-Authorization':'Bearer '+token,'Redirect-HTTP-Authorization':'Bearer '+token})[0]==401
        for shape in ['empty-primary','single-redirect','direct']:
            assert request(path=endpoint+'&forwarding_case='+shape,authorization='Bearer '+token)[0]==404,shape
        assert request(path=endpoint+'&forwarding_case=invalid-primary',authorization='Bearer '+token)[0]==401
        # Negative control reproduces the original failure: in an Action-style
        # CGI handler outside /workouts, CGIPassAuth in .htaccess is insufficient.
        without_bridge='\n'.join(line for line in rendered.splitlines() if not line.startswith(('RewriteCond %{HTTP:Authorization}', 'RewriteRule ^api/assistant')))+'\n'
        htaccess.write_text(without_bridge)
        assert request(authorization='Bearer '+token)[0]==401,'Negative control should reproduce dropped Authorization'
        htaccess.write_text(rendered)
        # A host/handler may omit CGI Authorization even with CGIPassAuth On.
        # The explicit rewrite environment bridge must suffice independently.
        htaccess.write_text(rendered.replace('CGIPassAuth On','CGIPassAuth Off'))
        status,_=request(authorization='Bearer '+token)
        assert status==404,f'Rewrite environment bridge absent: HTTP {status}'
        assert request()[0]==401
        assert request(authorization='Bearer '+'0'*64)[0]==401
        # Header forwarding grants no website login or CSRF bypass.
        assert request(path=f'http://127.0.0.1:{port}/workouts/api/sync.php',authorization='Bearer '+token)[0]==401
        status,body=request(path=f'http://127.0.0.1:{port}/workouts/',authorization='Bearer '+token)
        assert status==200 and b'Sign in' in body
        print('PASS: reproduced missing-header 401; real Apache rewrite/CGI bearer forwarding with native forwarding on/off; missing/invalid/Basic/cookie rejection; website and sync remain gated (no database)')
    finally:
        server.terminate();server.wait(timeout=5);server.stderr.close()
