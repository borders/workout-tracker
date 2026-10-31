"""Local-only migration regression tests; create/drop an isolated database."""
import json,os,subprocess,tempfile
from pathlib import Path
import copy,shutil,uuid
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
     def set_(id,weight,exercise='Barbell bench press',kind='reps'):return dict(id=id,reps=3,weight=weight,exercise=exercise,kind=kind,notes='preserve',raw='original line',flags=[])
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
finally:
    admin('DROP DATABASE '+name)
