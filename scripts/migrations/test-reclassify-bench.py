"""Local-only migration regression tests; create/drop an isolated database."""
import json,os,subprocess,tempfile
from pathlib import Path
import copy,shutil,uuid,time
root=Path(__file__).resolve().parents[2]
php=os.environ.get('PHP_BINARY') or shutil.which('php')
assert php, 'Set PHP_BINARY to a PHP 8.1+ executable'
template_path=os.environ.get('FIELDWORK_MIGRATION_TEST_CONFIG')
assert template_path, 'Set FIELDWORK_MIGRATION_TEST_CONFIG to a local disposable MySQL admin configuration'
template=json.load(open(template_path))
assert template['host'] in ('localhost','127.0.0.1'), 'Refusing non-local database configuration'
name='fw_bench_test_'+uuid.uuid4().hex[:16]
env=dict(os.environ,FIELDWORK_CONFIG=template_path)
bootstrap='require '+json.dumps(str(root/'server/api/lib.php'))+'; $db=connect(configuration()); '
admin_env=dict(env)
def admin(sql):
    subprocess.run([php,'-r',bootstrap+'$db->exec('+json.dumps(sql)+');'],env=admin_env,check=True,capture_output=True,text=True)
admin('CREATE DATABASE '+name+' CHARACTER SET utf8mb4 COLLATE utf8mb4_bin')
try:
    with tempfile.TemporaryDirectory(prefix='bench-review-') as tmp:
     p=Path(tmp);cfg=dict(template);cfg['database']=name
     config=p/'config.json';config.write_text(json.dumps(cfg));config.chmod(0o600);env['FIELDWORK_CONFIG']=str(config)
     def call(code,data=None):
      code='require '+json.dumps(str(root/'server/api/lib.php'))+'; $db=connect(configuration()); '+code
      r=subprocess.run([php,'-r',code],input=json.dumps(data) if data is not None else None,text=True,env=env,capture_output=True,check=True);return json.loads(r.stdout) if r.stdout else None
     def set_(id,weight,exercise='Barbell bench press',kind='reps'):return dict(id=id,reps=3,weight=weight,exercise=exercise,kind=kind,notes='preserve',raw='original line',flags=[],extra={'emptyObject':{},'emptyArray':[]})
     def workout(id,sets):return dict(id=id,date='2026-10-20',dateLabel='2026-10-20',location='synthetic',notes='preserve notes',raw='original text',flags=[],sets=sets,updatedAt='2026-10-20T00:00:00Z',context={},extra={'emptyObject':{},'emptyArray':[],'nested':[{},[],{'0':'zero','1':{}}]})
     docs=[workout('import-light',[set_('light-a',55),set_('light-b',60)]),workout('import-heavy',[set_('heavy-a',45),set_('heavy-b',225)]),workout('import-mixed',[set_('mixed-a',55),set_('mixed-b',60,'Dumbbell bench press')])]
     call('migrate($db); $db->exec("DELETE FROM fw_records; DELETE FROM fw_operations; UPDATE fw_meta SET revision=3 WHERE id=1");$docs=json_decode(stream_get_contents(STDIN),false);foreach($docs as $i=>$doc){$q=$db->prepare("INSERT INTO fw_records(kind,id,revision,deleted,document) VALUES(?,?,?,?,?)");$q->execute(["workouts",$doc->id,$i+1,0,json_encode($doc)]);}',docs)
     snapshot=lambda:call('echo json_encode([$db->query("SELECT * FROM fw_records ORDER BY id")->fetchAll(PDO::FETCH_ASSOC),$db->query("SELECT * FROM fw_meta")->fetchAll(PDO::FETCH_ASSOC),$db->query("SELECT * FROM fw_operations")->fetchAll(PDO::FETCH_ASSOC)]);')
     script=[php,str(root/'scripts/migrations/reclassify-bench.php')]
     before=snapshot();report=p/'candidates.json';r=subprocess.run(script+['scan',str(report)],env=env,text=True,capture_output=True,preexec_fn=lambda:os.umask(0o022));assert r.returncode==0,r.stderr;assert snapshot()==before
     cs=json.loads(report.read_text())['candidates'];assert {x['workoutId']for x in cs}=={'import-light','import-mixed'}
     print('PASS: scan is database read-only; candidates include light/mixed sessions and exclude heavy barbell sessions')
     assert report.stat().st_mode&0o777==0o600
     print('PASS: candidate report is mode 0600 under umask 022')
     existing=report.read_bytes();r=subprocess.run(script+['scan',str(report)],env=env,capture_output=True);assert r.returncode!=0 and report.read_bytes()==existing
     dangling=p/'dangling.json';target=p/'never-created.json';dangling.symlink_to(target);r=subprocess.run(script+['scan',str(dangling)],env=env,capture_output=True);assert r.returncode!=0 and not target.exists() and dangling.is_symlink()
     race=p/'race.json';jobs=[subprocess.Popen(script+['scan',str(race)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,preexec_fn=lambda:os.umask(0o022))for _ in range(2)];results=[(j.communicate(),j.wait()) for j in jobs];assert sorted(r[1]for r in results)==[0,1];assert json.loads(race.read_text())['candidates']==cs;assert race.stat().st_mode&0o777==0o600
     print('PASS: existing outputs and symlinks are refused; concurrent scans produce exactly one complete private report')
     approval=p/'approved.json';approval.write_text(json.dumps({'changes':[{'workoutId':'import-light','revision':1,'setIds':['light-a']}]}));backup=p/'before.json'
     r=subprocess.run(script+['apply',str(approval),str(backup)],env=env,text=True,capture_output=True);assert r.returncode==0,r.stderr
     after=snapshot();doc=json.loads(next(x for x in after[0] if x['id']=='import-light')['document']);assert doc['sets'][0]['exercise']=='Dumbbell bench press';assert doc['sets'][1]['exercise']=='Barbell bench press';assert doc['raw']==docs[0]['raw'];assert backup.stat().st_mode&0o777==0o600
     print('PASS: only approved set changes exercise; raw source retained; before-state backup is mode 0600')
     expected=copy.deepcopy(docs[0]);expected['sets'][0]['exercise']='Dumbbell bench press';assert doc==expected
     assert json.loads(json.loads(backup.read_text())['originalRecords'][0]['document'])==docs[0]
     print('PASS: complete document and backup preserve empty/nested/numeric-keyed objects and arrays; only approved exercise changed')
     r=subprocess.run(script+['apply',str(approval),str(p/'rerun.json')],env=env,text=True,capture_output=True);assert r.returncode!=0;assert snapshot()==after
     print('PASS: repeated apply with stale revision is rejected without additional writes')
     approval.write_text(json.dumps({'changes':[{'workoutId':'import-mixed','revision':3,'setIds':['missing']}]}));r=subprocess.run(script+['apply',str(approval),str(p/'invalid.json')],env=env,text=True,capture_output=True);assert r.returncode!=0;assert snapshot()==after
     print('PASS: unknown set approval is rejected without writes')
     # Batch includes a valid first update and a stale second approval: no writes.
     current=next(x for x in after[0] if x['id']=='import-light')['revision']
     batch={'changes':[{'workoutId':'import-light','revision':int(current),'setIds':['light-b']},{'workoutId':'import-mixed','revision':3,'setIds':['mixed-a']}]}
     approval.write_text(json.dumps({**batch,'changes':[batch['changes'][0],{**batch['changes'][1],'revision':2}]}))
     r=subprocess.run(script+['apply',str(approval),str(p/'stale-batch.json')],env=env,capture_output=True);assert r.returncode!=0 and snapshot()==after
     approval.write_text(json.dumps(batch))
     # Fail the second operation after earlier writes have run inside the transaction.
     call("$db->exec(\"CREATE TRIGGER bench_fail BEFORE INSERT ON fw_operations FOR EACH ROW BEGIN IF JSON_UNQUOTE(JSON_EXTRACT(NEW.request_json,'$.id'))='import-mixed' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='synthetic failure'; END IF; END\");")
     r=subprocess.run(script+['apply',str(approval),str(p/'fault-batch.json')],env=env,capture_output=True);assert r.returncode!=0 and snapshot()==after
     call('$db->exec("DROP TRIGGER bench_fail");')
     print('PASS: stale second approval and second-write SQL failure leave all workouts, revisions, and audit receipts unchanged')
     # Pause the second audit insert using a test-only SQL trigger, not a production failpoint.
     marker='bench-stop-'+uuid.uuid4().hex
     call("$db->exec(\"CREATE TRIGGER bench_pause BEFORE INSERT ON fw_operations FOR EACH ROW BEGIN IF JSON_UNQUOTE(JSON_EXTRACT(NEW.request_json,'$.id'))='import-mixed' THEN DO GET_LOCK('"+marker+"',0); DO SLEEP(20); END IF; END\");")
     proc=subprocess.Popen(script+['apply',str(approval),str(p/'interrupted.json')],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
     try:
      deadline=time.monotonic()+10;owner=None
      while time.monotonic()<deadline:
       owner=call("echo json_encode($db->query(\"SELECT IS_USED_LOCK('"+marker+"')\")->fetchColumn());")
       if owner:break
       time.sleep(.05)
      assert owner, 'Migration did not reach the second write'
      assert snapshot()==after, 'Another reader saw uncommitted migration data'
      proc.kill();proc.communicate(timeout=5)
      call('$db->exec("KILL CONNECTION '+str(int(owner))+'");')
      # Wait for rollback/release of the writer lock, rather than merely reading an old snapshot.
      call('$db->beginTransaction();$db->query("SELECT revision FROM fw_meta WHERE id=1 FOR UPDATE");$db->rollBack();')
      assert snapshot()==after
     finally:
      if proc.poll() is None:proc.kill();proc.communicate()
      call('$db->exec("DROP TRIGGER bench_pause");')
     print('PASS: a killed CLI/database connection rolls the entire batch back; concurrent readers see no partial data')
     r=subprocess.run(script+['apply',str(approval),str(p/'complete-batch.json')],env=env,text=True,capture_output=True);assert r.returncode==0,r.stderr
     final=snapshot();assert int(final[1][0]['revision'])==int(after[1][0]['revision'])+2;assert len(final[2])==len(after[2])+2
     expected_light=copy.deepcopy(expected);expected_light['sets'][1]['exercise']='Dumbbell bench press'
     expected_mixed=copy.deepcopy(docs[2]);expected_mixed['sets'][0]['exercise']='Dumbbell bench press'
     assert json.loads(next(x for x in final[0] if x['id']=='import-light')['document'])==expected_light
     assert json.loads(next(x for x in final[0] if x['id']=='import-mixed')['document'])==expected_mixed
     backup_data=json.loads((p/'complete-batch.json').read_text());assert len(backup_data['operationIds'])==2
     r=subprocess.run(script+['apply',str(approval),str(p/'repeat-batch.json')],env=env,capture_output=True);assert r.returncode!=0 and snapshot()==final
     print('PASS: successful batch commits every approved workout and audit receipt exactly once, with operation IDs retained in the private backup')
finally:
    admin('DROP DATABASE '+name)
