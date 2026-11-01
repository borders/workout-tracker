"""Run only through run-assistant-tests.py (its isolated DB/private directory)."""
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

root=Path(__file__).resolve().parent.parent
private=Path(os.environ['ASSISTANT_TEST_PRIVATE'])
assert private.name.startswith('assistant-test-')
assert json.loads(Path(os.environ['FIELDWORK_CONFIG']).read_text())['database'].startswith('fw_assistant_test_')
base=os.environ['ASSISTANT_TEST_ROOT']+'/assistant.php'
assert base.startswith('http://127.0.0.1:')
php=os.environ['PHP_BINARY']
token=os.environ['ASSISTANT_TEST_TOKEN']
security=private/'assistant-private'

def request(secret=token,query='action=recent',body=None,**headers):
    headers={'Authorization':'Bearer '+secret,**headers}
    try:
        with urlopen(Request(base+'?'+query,data=body,headers=headers),timeout=10) as r:
            return r.status,json.load(r),r.headers
    except HTTPError as e:
        return e.code,json.load(e),e.headers

def reset_rates():
    # No production knobs: tests alone reset local fixture counters.
    for path in security.glob('rate-*.json'):path.unlink()

def command(*args,success=True):
    result=subprocess.run([php,str(root/'scripts/assistant/token.php'),*args],env=os.environ,capture_output=True)
    assert (result.returncode==0)==success
    assert token.encode() not in result.stdout+result.stderr
    return result

def php_run(code):
    result=subprocess.run([php,'-r','require '+json.dumps(str(root/'server/api/lib.php'))+';$db=connect(configuration());'+code],env=os.environ,capture_output=True,check=True)
    return result.stdout.decode()

reset_rates()
# Auth is exclusively a bearer header; query/cookie values cannot authenticate.
assert request('',query='action=recent&token='+token,Cookie='assistant-token='+token)[0]==401
assert request(token,query='action[]=recent')[0]==404
assert request(token,query='action=recent&limit[]=2')[0]==400
assert request(token,query='action=recent&limit=21')[0]==400
assert request(query='action=append_set',body=b'{',**{'Content-Type':'application/json'})[0]==400
assert request(query='action=append_set',body=b'x'*16385,**{'Content-Type':'application/json'})[0]==413
assert request(query='action=append_set',body=b'{}',**{'Content-Type':'application/json-evil'})[0]==415
assert request(query='action=recent',body=b'{}')[2]['Allow']=='GET'
# Limits hold inside one window, independent of failed auth and spoofed proxies.
reset_rates()
window=int(time.time())//60
for _ in range(20):assert request('0'*64)[0]==401
status,body,headers=request('0'*64,**{'X-Forwarded-For':'192.0.2.44'})
if int(time.time())//60!=window:
    raise RuntimeError('Rate tests crossed a minute boundary; rerun suite')
assert status==429 and 1<=int(headers['Retry-After'])<=60
assert request()[0]==200,'Failed authentication must not exhaust valid-token budget'
# Populate a full current window without waiting or depending on loop timing.
(security/'rate-authenticated.json').write_text(json.dumps({'window':int(time.time())//60,'count':120}))
assert request()[0]==429
reset_rates()
(security/'rate-writes.json').write_text(json.dumps({'window':int(time.time())//60,'count':30}))
assert request(query='action=append_set',body=b'{}',**{'Content-Type':'application/json'})[0]==429
assert request()[0]==200,'Write budget must not disable reads'
(security/'rate-authenticated.json').write_text(json.dumps({'window':int(time.time())//60-1,'count':120}))
assert request()[0]==200,'New windows must recover automatically'
# Failure to write/lock security state fails closed, with no raw error details.
(security/'rate-authenticated.json').write_text('{broken secret-private-marker')
status,body,_=request()
assert status==503 and body=={'error':'Assistant API unavailable'}
reset_rates()
# Generated date index follows browser updates and tombstones without app hooks.
php_run('migrate($db);migrate($db);')
plan=json.loads(php_run('echo json_encode($db->query("EXPLAIN SELECT id,revision,document FROM fw_records FORCE INDEX (assistant_recent) WHERE kind=\'workouts\' AND deleted=0 ORDER BY workout_date DESC,id DESC LIMIT 5")->fetchAll(PDO::FETCH_ASSOC));'))
assert plan[0]['key']=='assistant_recent' and 'filesort' not in plan[0]['Extra'].lower(),plan
status,recent,_=request(query='action=recent&limit=3')
assert status==200 and len(recent['workouts'])==3
assert [(w['date'][:10],w['id']) for w in recent['workouts']]==sorted([(w['date'][:10],w['id']) for w in recent['workouts']],reverse=True)
# Bound serialized output, not just row count. Projection automatically follows
# common sync upserts and tombstones without requiring Assistant-specific writes.
php_run("""
foreach(['cap-a','cap-b'] as $id){
 $doc=['id'=>$id,'date'=>'2099-01-01','dateLabel'=>'2099-01-01','location'=>str_repeat('x',600000),'notes'=>'','raw'=>'','flags'=>[],'sets'=>[],'updatedAt'=>'2099-01-01T00:00:00Z'];
 pushOperation($db,['operationId'=>$id,'kind'=>'workouts','id'=>$id,'baseRevision'=>0,'deleted'=>false,'document'=>$doc]);
}
""")
assert request(query='action=recent&limit=2')[0]==413
status,single,_=request(query='action=recent&limit=1')
assert status==200 and single['workouts'][0]['id']=='cap-b'
php_run("""
$row=$db->query("SELECT revision,document FROM fw_records WHERE kind='workouts' AND id='cap-a'")->fetch(PDO::FETCH_ASSOC);
$doc=json_decode($row['document'],true);$doc['date']='1900-01-01';
pushOperation($db,['operationId'=>'cap-update','kind'=>'workouts','id'=>'cap-a','baseRevision'=>(int)$row['revision'],'deleted'=>false,'document'=>$doc]);
$row=$db->query("SELECT revision FROM fw_records WHERE kind='workouts' AND id='cap-b'")->fetch(PDO::FETCH_ASSOC);
pushOperation($db,['operationId'=>'cap-delete','kind'=>'workouts','id'=>'cap-b','baseRevision'=>(int)$row['revision'],'deleted'=>true,'document'=>null]);
""")
status,updated,_=request(query='action=recent&limit=3')
assert status==200 and not any(w['id'].startswith('cap-') for w in updated['workouts'])
# A database failure after updating the document must roll back revision, JSON,
# and audit receipt together. An identical retry after recovery succeeds once.
workout_id=recent['workouts'][0]['id']
entry={'workoutId':workout_id,'idempotencyKey':'failure-retry-test-unique','exercise':'Barbell bench press','weight':135,'reps':5,'notes':'private-workout-notes-marker'}
def snapshot():
    return php_run("echo json_encode([$db->query(\"SELECT revision FROM fw_meta\")->fetchAll(PDO::FETCH_ASSOC),$db->query(\"SELECT id,revision,SHA2(document,256) AS digest FROM fw_records ORDER BY kind,id\")->fetchAll(PDO::FETCH_ASSOC),$db->query(\"SELECT COUNT(*) FROM fw_operations\")->fetchColumn()]);")
before=snapshot()
php_run("$db->exec(\"CREATE TRIGGER assistant_fault BEFORE INSERT ON fw_operations FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='secret-private-marker'\");")
status,body,_=request(query='action=append_set',body=json.dumps(entry).encode(),**{'Content-Type':'application/json'})
assert status==503 and body=={'error':'Assistant API unavailable'}
assert snapshot()==before,'Failed append must not persist any document/revision/audit changes'
php_run("$db->exec('DROP TRIGGER assistant_fault');")
status,receipt,_=request(query='action=append_set',body=json.dumps(entry).encode(),**{'Content-Type':'application/json'})
assert status==200 and receipt['saved']
assert request(query='action=append_set',body=json.dumps(entry).encode(),**{'Content-Type':'application/json'})[1]==receipt
# A held browser writer lock times out, rolls back, and remains retryable.
bootstrap='require '+json.dumps(str(root/'server/api/lib.php'))+';$db=connect(configuration());'
locker=subprocess.Popen([php,'-r',bootstrap+"$db->beginTransaction();$db->query('SELECT revision FROM fw_meta WHERE id=1 FOR UPDATE');echo 'locked';fflush(STDOUT);sleep(15);"],env=os.environ,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
try:
    assert locker.stdout.read(6)==b'locked'
    entry['idempotencyKey']='lock-retry-test-unique'
    before=snapshot();started=time.monotonic()
    status,body,_=request(query='action=append_set',body=json.dumps(entry).encode(),**{'Content-Type':'application/json'})
    assert status==503 and time.monotonic()-started<8
    assert snapshot()==before
finally:
    locker.terminate();locker.wait(timeout=5)
assert request(query='action=append_set',body=json.dumps(entry).encode(),**{'Content-Type':'application/json'})[0]==200
# Old-schema upgrade and missing-schema failure: no DDL or unbounded fallback in HTTP.
php_run("$db->exec('ALTER TABLE fw_records DROP INDEX assistant_recent');")
assert request()[0]==503
php_run("$db->exec('ALTER TABLE fw_records DROP COLUMN workout_date');migrate($db);")
assert request()[0]==200
# No plaintext token in server credential state; never accept legacy token files.
assert token not in (security/'credential.json').read_text()
(private/'assistant-token').write_text(token)
command('provision',str(private/'must-not-create'),success=False)
command('rotate',str(private/'bad-days'),'91',success=False)
command('rotate',str(private/'bad-days'),'0',success=False)
command('rotate',str(private/'issued-token'),success=False) # refuse overwrites
assert request()[0]==200
output=private/'rotated-token'
command('rotate',str(output),'1')
new=output.read_text().strip()
assert len(new)==64 and output.stat().st_mode&0o777==0o600
assert request(token)[0]==401 and request(new)[0]==200
credential=security/'credential.json'
state=json.loads(credential.read_text());state['expires']=int(time.time())-1
credential.write_text(json.dumps(state))
assert request(new)[0]==401
command('rotate',str(private/'final-token'))
new=(private/'final-token').read_text().strip()
assert request(new)[0]==200
credential.write_text('{torn-private-state')
assert request(new)[0]==503
command('rotate',str(private/'recovered-token'))
new=(private/'recovered-token').read_text().strip()
assert request(new)[0]==200
command('revoke')
assert request(new)[0]==401 and request(token)[0]==401
# World-readable state and symlinked state are rejected even for valid tokens.
credential.chmod(0o644)
assert request(new)[0]==503
credential.chmod(0o600)
credential.unlink();credential.symlink_to(private/'assistant-token')
assert request(new)[0]==503
credential.unlink()
# Disabling credentials cannot affect ordinary browser sync authentication.
from http.cookiejar import CookieJar
from urllib.request import build_opener,HTTPCookieProcessor
opener=build_opener(HTTPCookieProcessor(CookieJar()))
with opener.open(os.environ['ASSISTANT_TEST_ROOT']+'/sync.php?action=handshake') as response:
    assert response.status==200 and json.load(response)['csrf']
print('PASS: request bounds/methods, separate abuse budgets, Retry-After/reset, fail-closed state/schema, indexed recent query over 500+ records, additive upgrade, hashed credentials, rotation/expiry/revocation, permissions/symlinks, transactional fault/lock-timeout recovery, and independent PWA sync auth')
