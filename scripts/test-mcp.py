"""Read-only MCP/OAuth integration, invoked by run-assistant-tests.py only.

Uses its disposable DB/REST server, a synthetic local issuer, and a second
loopback PHP listener. Never accepts a production target or production config.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler

root=Path(__file__).resolve().parent.parent
private=Path(os.environ['ASSISTANT_TEST_PRIVATE'])
assert private.name.startswith('assistant-test-')
config=json.loads(Path(os.environ['FIELDWORK_CONFIG']).read_text())
assert config['database'].startswith('fw_assistant_test_') and config['host'] in ('127.0.0.1','localhost')
backend=os.environ['ASSISTANT_TEST_ROOT']+'/assistant.php'
assert urlsplit(backend).hostname=='127.0.0.1'
php=os.environ['PHP_BINARY']
rest_token=os.environ['ASSISTANT_TEST_TOKEN']

def write(path, value):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as file:file.write(value)

def php_code(code, data=None):
    result=subprocess.run([php,'-r',code],input=None if data is None else json.dumps(data).encode(),capture_output=True,check=True,env=os.environ)
    return result.stdout.decode()

bootstrap='require '+json.dumps(str(root/'vendor/autoload.php'))+';'
keys=[]
for index in range(2):
    path=private/f'oauth-key-{index}.pem'
    jwk=json.loads(php_code('''$key=openssl_pkey_new(['private_key_bits'=>2048,'private_key_type'=>OPENSSL_KEYTYPE_RSA]);openssl_pkey_export($key,$pem);umask(0077);file_put_contents('''+json.dumps(str(path))+''',$pem);$details=openssl_pkey_get_details($key);$b64=fn($s)=>rtrim(strtr(base64_encode($s),'+/','-_'),'=');echo json_encode(['kty'=>'RSA','use'=>'sig','alg'=>'RS256','kid'=>'''+json.dumps('fixture-'+str(index))+''','n'=>$b64($details['rsa']['n']),'e'=>$b64($details['rsa']['e'])]);'''))
    keys.append((path,jwk))

def sign(claims, index=0, typ='at+jwt', alg='RS256', extra=None):
    if alg=='HS256':key='str_repeat("x",64)'
    else:key='file_get_contents('+json.dumps(str(keys[index][0]))+')'
    return php_code(bootstrap+r'$claims=json_decode(stream_get_contents(STDIN),true);echo Firebase\JWT\JWT::encode($claims,'+key+','+json.dumps(alg)+','+json.dumps(keys[index][1]['kid'])+','+'json_decode('+json.dumps(json.dumps({'typ':typ,**(extra or {})}))+',true)'+');',claims)

published=[keys[0][1]]
provider_calls=[]
codes={}
resource=''
issuer=''
callback='http://127.0.0.1/callback'
class Provider(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def respond(self,status,data):
        body=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):pass
    def do_GET(self):
        provider_calls.append(self.path)
        if self.path=='/.well-known/oauth-authorization-server':
            self.respond(200,{'issuer':issuer,'jwks_uri':issuer+'keys','authorization_endpoint':issuer+'authorize','token_endpoint':issuer+'token','code_challenge_methods_supported':['S256'],'response_types_supported':['code'],'grant_types_supported':['authorization_code'],'token_endpoint_auth_methods_supported':['none']})
        elif self.path=='/keys':self.respond(200,{'keys':published})
        elif self.path.startswith('/authorize?'):
            params={k:v[0] for k,v in parse_qs(urlsplit(self.path).query).items()}
            if params.get('redirect_uri')!=callback or params.get('resource')!=resource or params.get('code_challenge_method')!='S256':self.respond(400,{});return
            code=secrets.token_urlsafe(24);codes[code]=params
            self.send_response(302);self.send_header('Location',callback+'?'+urlencode({'code':code,'state':params['state']}));self.end_headers()
        elif self.path=='/redirect':
            self.send_response(302);self.send_header('Location',issuer+'must-not-follow');self.end_headers()
        elif self.path=='/oversized':
            self.respond(200,{'large':'x'*1100000})
        elif self.path=='/stalled':
            self.send_response(200);self.end_headers();time.sleep(3)
            try:self.wfile.write(b'{}')
            except (BrokenPipeError,ConnectionResetError):pass
        else:self.respond(404,{})
    def do_POST(self):
        params={k:v[0] for k,v in parse_qs(self.rfile.read(int(self.headers.get('Content-Length','0'))).decode()).items()}
        original=codes.pop(params.get('code',''),None)
        if not original or params.get('redirect_uri')!=callback or params.get('resource')!=resource or original['code_challenge']!=base64.urlsafe_b64encode(hashlib.sha256(params.get('code_verifier','').encode()).digest()).decode().rstrip('='):
            self.respond(400,{'error':'invalid_grant'});return
        claims={'iss':issuer,'aud':resource,'sub':'fixture-owner','scope':'workouts:read','iat':int(time.time()),'exp':int(time.time())+300}
        self.respond(200,{'access_token':sign(claims),'token_type':'Bearer','expires_in':300,'scope':'workouts:read'})

provider=ThreadingHTTPServer(('127.0.0.1',0),Provider)
issuer=f'http://127.0.0.1:{provider.server_port}/'
thread=threading.Thread(target=provider.serve_forever,daemon=True);thread.start()
with socket.socket() as reservation:
    reservation.bind(('127.0.0.1',0));port=reservation.getsockname()[1]
resource=f'http://127.0.0.1:{port}/workouts/mcp'
metadata=f'http://127.0.0.1:{port}/workouts/.well-known/oauth-protected-resource'
path=private/'mcp-config.json'
write(private/'assistant-client-token.txt',rest_token+'\n')
router=private/'mcp-router.php'
write(router,'<?php $_SERVER["SCRIPT_NAME"]=parse_url($_SERVER["REQUEST_URI"],PHP_URL_PATH);require '+json.dumps(str(root/'dist/gate.php'))+';')
log=open(private/'mcp-test.log','w+b');os.chmod(private/'mcp-test.log',0o600)
env=dict(os.environ,FIELDWORK_MCP_TESTING='1',FIELDWORK_MCP_TEST_ASSISTANT_URL=backend)
server=subprocess.Popen([php,'-S',f'127.0.0.1:{port}',str(router)],env=env,stdout=subprocess.DEVNULL,stderr=log)

def call(body=None,token=None,url=resource,method=None,headers=None):
    headers=dict(headers or {})
    if token is not None:headers['Authorization']='Bearer '+token
    if body is not None:
        data=json.dumps(body).encode();headers.setdefault('Content-Type','application/json');headers.setdefault('Accept','application/json, text/event-stream')
    else:data=None
    try:
        response=urlopen(Request(url,data=data,headers=headers,method=method),timeout=15)
    except HTTPError as error:response=error
    raw=response.read()
    try:parsed=json.loads(raw) if raw else None
    except ValueError:parsed=raw.decode()
    return response.status,parsed,response.headers

hello={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'synthetic-test','version':'1'}}}
try:
    for _ in range(100):
        try:
            with socket.create_connection(('127.0.0.1',port),timeout=.1):break
        except OSError:time.sleep(.05)
    # Direct HTTP adapter checks use only this synthetic loopback server.
    http_bootstrap=bootstrap+'require '+json.dumps(str(root/'server/mcp/config.php'))+';require '+json.dumps(str(root/'server/mcp/Http.php'))+';'
    status=php_code(http_bootstrap+'echo mcpBoundedGet('+json.dumps(issuer+'redirect')+',[],1000)->getStatusCode();')
    assert status=='302' and '/must-not-follow' not in provider_calls
    for endpoint in ['oversized','stalled']:
        started=time.monotonic()
        rejected=php_code(http_bootstrap+'try{mcpBoundedGet('+json.dumps(issuer)+'.'+json.dumps(endpoint)+',[],1048576);echo "accepted";}catch(Throwable $e){echo "rejected";}')
        assert rejected=='rejected' and time.monotonic()-started<9,endpoint
    no_network=php_code(http_bootstrap+'$client=new McpIssuerClient("https://issuer.invalid/");try{$client->sendRequest(new Nyholm\\Psr7\\Request("GET","https://different.invalid/keys"));echo "accepted";}catch(McpNetworkFailure $e){echo "rejected";}')
    assert no_network=='rejected'
    assert call(hello)[0]==404,'MCP must be disabled without configuration'
    write(path,json.dumps({'enabled':True,'resource':resource,'issuer':issuer,'owner_subject':'fixture-owner'}))
    status,document,_=call(url=metadata)
    assert status==200 and document['resource']==resource and document['authorization_servers']==[issuer]
    assert document['scopes_supported']==['workouts:read']
    assert call(url=metadata,headers={'Origin':'https://chatgpt.com'})[2]['Access-Control-Allow-Origin']=='https://chatgpt.com'
    status,_,challenge=call(hello)
    assert status==401 and ('resource_metadata="'+metadata+'"') in challenge['WWW-Authenticate']
    # Follow discovery through a synthetic provider's code/PKCE exchange. No
    # provider account or production OAuth registration is used or claimed.
    verifier=secrets.token_urlsafe(48)
    challenge_value=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    state=secrets.token_urlsafe(24)
    params={'response_type':'code','client_id':'fixture-client','redirect_uri':callback,'scope':'workouts:read','resource':resource,'state':state,'code_challenge':challenge_value,'code_challenge_method':'S256'}
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self,*args):return None
    def code_request():
        try:build_opener(NoRedirect()).open(issuer+'authorize?'+urlencode(params))
        except HTTPError as error:
            assert error.code==302
            result=parse_qs(urlsplit(error.headers['Location']).query);assert result['state']==[state]
            return result['code'][0]
    def exchange(code, secret):
        body=urlencode({'grant_type':'authorization_code','client_id':'fixture-client','code':code,'redirect_uri':callback,'resource':resource,'code_verifier':secret}).encode()
        try:response=urlopen(Request(issuer+'token',data=body,headers={'Content-Type':'application/x-www-form-urlencoded'}))
        except HTTPError as error:response=error
        return response.status,json.load(response)
    assert exchange(code_request(),'wrong-verifier')[0]==400
    code=code_request();status,tokens=exchange(code,verifier)
    assert status==200
    access=tokens['access_token']
    assert exchange(code,verifier)[0]==400,'Authorization codes must be single use in fixture'
    status,initialized,headers=call(hello,access)
    assert status==200 and initialized['result']['serverInfo']['name']=='Fieldwork read-only',(status,initialized)
    session=headers.get('Mcp-Session-Id')
    assert session
    rpc_headers={'Mcp-Session-Id':session,'Mcp-Protocol-Version':'2025-11-25'}
    assert call({'jsonrpc':'2.0','method':'notifications/initialized'},access,headers=rpc_headers)[0]==202
    def rpc(method,arguments=None,token=access):
        message={'jsonrpc':'2.0','id':2,'method':method}
        if arguments is not None:message['params']=arguments
        return call(message,token,headers=rpc_headers)
    status,listed,_=rpc('tools/list')
    assert status==200 and [t['name'] for t in listed['result']['tools']]==['recent_workouts'],listed
    tool=listed['result']['tools'][0]
    assert tool['annotations']['readOnlyHint'] is True
    assert tool['inputSchema']['additionalProperties'] is False
    assert tool['_meta']['securitySchemes'][0]['scopes']==['workouts:read']
    modern_meta={'io.modelcontextprotocol/protocolVersion':'2026-07-28','io.modelcontextprotocol/clientCapabilities':{}}
    modern_headers={'Mcp-Protocol-Version':'2026-07-28','Mcp-Method':'tools/list'}
    modern={'jsonrpc':'2.0','id':3,'method':'tools/list','params':{'_meta':modern_meta}}
    status,new_list,_=call(modern,access,headers=modern_headers)
    assert status==200 and new_list['result']['tools'][0]['name']=='recent_workouts',new_list
    status,stream_denied,_=rpc('subscriptions/listen',{})
    assert status==200 and stream_denied.get('error',{}).get('code')==-32601
    # Snapshot all database content/revisions/receipts before and after reads.
    db_bootstrap='require '+json.dumps(str(root/'server/api/lib.php'))+';$db=connect(configuration());'
    snapshot_code=db_bootstrap+'''echo json_encode([$db->query("SELECT * FROM fw_meta")->fetchAll(PDO::FETCH_ASSOC),$db->query("SELECT kind,id,revision,deleted,SHA2(document,256) AS digest FROM fw_records ORDER BY kind,id")->fetchAll(PDO::FETCH_ASSOC),$db->query("SELECT id,request_hash FROM fw_operations ORDER BY id")->fetchAll(PDO::FETCH_ASSOC)]);'''
    before=php_code(snapshot_code)
    status,recent,_=rpc('tools/call',{'name':'recent_workouts','arguments':{'limit':5}})
    assert status==200 and recent.get('result',{}).get('isError') is False,recent
    expected=call(token=rest_token,url=backend+'?action=recent&limit=5')[1]
    assert recent['result']['structuredContent']==expected,'REST fields/JSON objects changed'
    for args in [{'limit':0},{'limit':21},{'limit':1.5},{'limit':'5'},{'url':'http://127.0.0.1/evil'},{'action':'append_set'}]:
        _,result,_=rpc('tools/call',{'name':'recent_workouts','arguments':args})
        assert result.get('error') or result.get('result',{}).get('isError'),result
    for name in ['append_set','delete_workout','sync']:
        _,result,_=rpc('tools/call',{'name':name,'arguments':{}})
        assert result.get('error'),result
    claims={'iss':issuer,'aud':resource,'sub':'fixture-owner','scope':'workouts:read','iat':int(time.time()),'exp':int(time.time())+300}
    for changed,expected_status in [({'iss':issuer+'wrong'},401),({'aud':'other-resource'},401),({'sub':'someone-else'},403),({'scope':'workouts:write'},403),({'exp':int(time.time())-60},401),({'exp':int(time.time())+7200},401),({'iat':int(time.time())+100},401),({'exp':None},401)]:
        rejected,_,rejection_headers=call(hello,sign({**claims,**changed}))
        assert rejected==expected_status,(changed,rejected,expected_status,rejection_headers.get('WWW-Authenticate'))
    segments=access.split('.')
    segments[2]=('A' if segments[2][0]!='A' else 'B')+segments[2][1:]
    assert call(hello,'.'.join(segments))[0]==401,'Invalid signature'
    assert call(hello,sign(claims,typ='JWT'))[0]==401,'ID tokens must not authorize reads'
    assert call(hello,sign(claims,alg='HS256'))[0]==401,'Algorithm confusion'
    assert call(hello,sign(claims,index=1))[0]==401,'Unpublished signing key'
    published.append(keys[1][1])
    assert call(hello,sign(claims,index=1))[0]==200,'JWKS rotation must refresh unknown key'
    assert call(hello,sign(claims,extra={'jku':'https://evil.example/keys'}))[0]==200,'Token jku must be ignored, using issuer-pinned keys'
    assert call(hello,rest_token)[0]==401,'REST token must not authorize MCP'
    assert call(hello,headers={'Cookie':'fieldwork_login=synthetic'})[0]==401
    assert call(hello,headers={'Redirect-HTTP-Authorization':'Bearer '+access})[0]==401
    assert call(hello,access,headers={'Origin':'https://evil.example'})[0]==403
    assert call(hello,access,headers={'Host':'evil.example'})[0]==403
    assert call([hello,hello],access)[0]==400
    assert call({'oversized':'x'*17000},access)[0]==413
    assert call(hello,access,headers={'Content-Type':'text/plain'})[0]==415
    assert call(token=access)[0]==405
    # Backend credential failure is a generic tool error, not leaked headers or
    # exception details, and must never fall back to website/owner credentials.
    token_path=private/'assistant-client-token.txt';original=token_path.read_text()
    token_path.write_text('0'*64+'\n')
    _,failed,_=rpc('tools/call',{'name':'recent_workouts','arguments':{}})
    assert failed['result']['isError'] is True and 'Nothing was changed' in failed['result']['content'][0]['text']
    token_path.write_text(original)
    token_path.chmod(0o644)
    _,failed,_=rpc('tools/call',{'name':'recent_workouts','arguments':{}})
    assert failed['result']['isError'] is True
    token_path.chmod(0o600)
    assert php_code(snapshot_code)==before,'Read-only MCP changed database content'
    rate=private/'mcp-private/rate-owner.json'
    rate.write_text(json.dumps({'window':int(time.time())//60,'count':120}))
    status,_,rate_headers=call(hello,access)
    assert status==429 and 1<=int(rate_headers['Retry-After'])<=60
    rate.write_text(json.dumps({'window':int(time.time())//60-1,'count':120}))
    assert call(hello,access)[0]==200
    for stored in (private/'mcp-private').rglob('*'):
        if stored.is_file():
            assert stored.stat().st_mode&0o777==0o600
            content=stored.read_bytes()
            assert rest_token.encode() not in content and access.encode() not in content,'Credentials persisted in MCP session/cache'
        elif stored.is_dir():assert stored.stat().st_mode&0o777==0o700
    path.chmod(0o644)
    assert call(hello,access)[0]==503
    path.chmod(0o600)
    # Toggle is read on each request, including existing authenticated sessions.
    path.write_text(json.dumps({'enabled':False}))
    assert call(hello,access)[0]==404 and call(url=metadata)[0]==404
    log.flush();log.seek(0);logs=log.read()
    for secret in [rest_token,access,tokens['access_token']]:assert secret.encode() not in logs,'Credential leaked to PHP logs'
    print('PASS: disabled-by-default MCP, metadata/challenge discovery, synthetic code+PKCE flow, owner/issuer/audience/expiry/type/algorithm/scope checks, JWKS rotation, real REST read bridge with JSON preservation, no write tools, request bounds, secret failure handling, revocation toggle, unchanged database, and safe logs')
finally:
    server.terminate();server.wait(timeout=5);log.close()
    provider.shutdown();provider.server_close();thread.join(timeout=5)
