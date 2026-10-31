<?php
declare(strict_types=1);
/**
 * One-time bench classification repair. CLI ONLY; never called by a web request.
 *
 * php scripts/migrations/reclassify-bench.php scan [output.json]
 * php scripts/migrations/reclassify-bench.php apply approvals.json /absolute/private/backup.json
 *
 * Approval JSON: {"changes":[{"workoutId":"import-...","revision":12,
 * "setIds":["uuid", "..."]}]}
 * Only exact approved sets are modified; every change requires an unchanged revision.
 */
if (PHP_SAPI !== 'cli') { http_response_code(404); exit; }
require dirname(__DIR__, 2).'/server/api/lib.php';
function failMigration(string $message): never { fwrite(STDERR, $message."\n"); exit(1); }
// Create privately from the first byte, with no exists/check/write race.
function writePrivateFile(string $path,string $payload): void {
    $parent=realpath(dirname($path));
    if(!$parent || (fileperms($parent)&0077)!==0)throw new RuntimeException('Output requires a private parent directory (chmod 700).');
    $path=$parent.'/'.basename($path);
    if(is_link($path))throw new RuntimeException('Refusing a symlink output path.');
    $previous=umask(0077);
    try{$handle=@fopen($path,'xb');}finally{umask($previous);}
    if(!$handle)throw new RuntimeException('Cannot exclusively create output; it may already exist.');
    try{
        $offset=0;$length=strlen($payload);
        while($offset<$length){$written=fwrite($handle,substr($payload,$offset));if($written===false||$written===0)throw new RuntimeException('Incomplete output write.');$offset+=$written;}
        if(!fflush($handle))throw new RuntimeException('Could not flush output.');
        if(function_exists('fsync')&&!fsync($handle))throw new RuntimeException('Could not persist output.');
        if(!fclose($handle))throw new RuntimeException('Could not close output.');
    }catch(Throwable $error){if(is_resource($handle))fclose($handle);@unlink($path);throw new RuntimeException('Output could not be completed. No migration writes performed.');}
}
function readWorkouts(PDO $db): array {
    return $db->query("SELECT id,revision,document FROM fw_records WHERE kind='workouts' AND deleted=0 ORDER BY id")->fetchAll(PDO::FETCH_ASSOC);
}
function candidates(array $rows): array {
    $out=[];
    foreach ($rows as $row) {
        $w=json_decode($row['document'],true,512,JSON_THROW_ON_ERROR);
        if(!str_starts_with($row['id'],'import-'))continue;
        $bench=array_values(array_filter($w['sets']??[],static fn($s)=>
            in_array($s['exercise']??'', ['Barbell bench press','Dumbbell bench press'],true)
            && ($s['kind']??'')==='reps'));
        if(!$bench)continue;
        $barbell=array_values(array_filter($bench,static fn($s)=>$s['exercise']==='Barbell bench press'));
        if(!$barbell)continue;
        $weights=array_column($barbell,'weight');
        sort($weights,SORT_NUMERIC);
        $max=max($weights);
        // A session with any bench set above the user's historical 110-lb
        // per-dumbbell ceiling is barbell by default; never suggest converting
        // that session's barbell sets. Explicit notes can be reviewed separately.
        $sessionHasHeavyBench=count(array_filter($bench,static fn($set)=>($set['weight']??0)>110))>0;
        if($sessionHasHeavyBench)continue;
        $count=count($barbell);
        $lightCount=count(array_filter($weights,static fn($weight)=>$weight>=35&&$weight<=100));
        $explicitDb=count($bench)-$count;
        // Entire sessions are evidence: a lone 45-lb barbell warmup alongside
        // heavier barbell work is not a candidate. Ambiguous sessions remain
        // visible with a reason and require human approval.
        $plausiblyDumbbell=$count>=2 && $lightCount===$count && $max<=100;
        $mixedExplicit=$explicitDb>0;
        if(!$plausiblyDumbbell && !$mixedExplicit)continue;
        $out[]=[
            'workoutId'=>$row['id'],'revision'=>(int)$row['revision'],
            'date'=>$w['dateLabel']??'','location'=>$w['location']??'',
            'reason'=>$plausiblyDumbbell
                ? 'All barbell-labelled bench working sets are in a typical dumbbell range; review entire session.'
                : 'Session contains explicitly labelled dumbbell sets; review for adjacent misclassifications.',
            'caution'=>$mixedExplicit
                ? 'Mixed exercise labels: check notes before approving any set.'
                : 'Weight is circumstantial evidence, not proof.',
            'suggestedSetIds'=>array_column($barbell,'id'),
            'allSets'=>array_map(static fn($s)=>[
                'id'=>$s['id'],'exercise'=>$s['exercise'],'weight'=>$s['weight'],
                'reps'=>$s['reps'],'notes'=>$s['notes']??'','raw'=>$s['raw']??''],
                $w['sets']??[]),
            'originalSessionNotes'=>$w['notes']??'',
        ];
    }
    return $out;
}
if($argc<2 || !in_array($argv[1],['scan','apply'],true))failMigration('Usage: scan [path] | apply approvals.json /absolute/private/backup.json');
$db=connect(configuration());
if($argv[1]==='scan') {
    $result=['warning'=>'Candidates only; NEVER automatic classification. Review complete sessions and original notes.','candidates'=>candidates(readWorkouts($db))];
    $json=json_encode($result,JSON_PRETTY_PRINT|JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR)."\n";
    if(isset($argv[2])) {
        try{writePrivateFile($argv[2],$json);}catch(Throwable $e){failMigration($e->getMessage());}
    } else echo $json;
    exit;
}
if($argc!==4)failMigration('Apply requires approval path AND absolute private backup path.');
[$script,$mode,$approvalPath,$backupPath]=$argv;
if(!str_starts_with($backupPath,'/') || file_exists($backupPath))failMigration('Backup must be a NEW absolute path outside the web root.');
$backupDir=realpath(dirname($backupPath));
if(!$backupDir || !is_dir($backupDir) || !is_writable($backupDir))failMigration('Backup parent directory is unavailable.');
if(str_contains($backupDir,'/public_html') || str_contains($backupDir,'/borderseng.com') || str_contains($backupDir,'/releases'))failMigration('Refusing a backup in a web/deployment directory.');
$plan=json_decode((string)file_get_contents($approvalPath),true,512,JSON_THROW_ON_ERROR);
if(!is_array($plan['changes']??null)||!count($plan['changes']))failMigration('Empty or invalid approval list.');
$engines=$db->query("SELECT TABLE_NAME,ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('fw_meta','fw_records','fw_operations')")->fetchAll(PDO::FETCH_KEY_PAIR);
if(count($engines)!==3 || count(array_filter($engines,static fn($engine)=>strtoupper($engine)!=='INNODB')))failMigration('Atomic apply requires all three sync tables to use InnoDB.');
$commitStarted=false;
$db->beginTransaction();
try{
    // Acquire the sync writer lock before reading any approved record. Readers
    // see the entire old or new batch; sync writers wait until commit/rollback.
    if(!$db->query('SELECT revision FROM fw_meta WHERE id=1 FOR UPDATE')->fetch(PDO::FETCH_ASSOC))throw new RuntimeException('Sync schema is not initialized.');
$rows=[];$ops=[];$seen=[];
foreach($plan['changes'] as $change) {
    $id=$change['workoutId']??null;$rev=$change['revision']??null;$ids=$change['setIds']??null;
    if(!is_string($id)||!str_starts_with($id,'import-')||!is_int($rev)||!is_array($ids)||!count($ids)||isset($seen[$id]))throw new RuntimeException('Invalid/duplicate approval entry.');
    $seen[$id]=true;$setIds=array_fill_keys($ids,true);
    if(count($setIds)!==count($ids))throw new RuntimeException('Duplicate set IDs.');
    $q=$db->prepare("SELECT revision,deleted,document FROM fw_records WHERE kind='workouts' AND id=? FOR UPDATE");$q->execute([$id]);$row=$q->fetch(PDO::FETCH_ASSOC);
    if(!$row || (int)$row['revision']!==$rev || (int)$row['deleted']!==0)throw new RuntimeException("Revision changed/missing: $id. Re-run scan.");
    // Objects must remain objects, including empty and numeric-keyed objects.
    $w=json_decode($row['document'],false,512,JSON_THROW_ON_ERROR);$changed=0;
    foreach($w->sets as $s) if(isset($setIds[$s->id])) {
        if($s->exercise!=='Barbell bench press')throw new RuntimeException("Not a barbell set: $id");
        $s->exercise='Dumbbell bench press';$changed++;unset($setIds[$s->id]);
    }
    unset($s);
    if($setIds || $changed!==count($ids))throw new RuntimeException("Unknown set IDs: $id");
    if(!validDocument('workouts',$id,$w))throw new RuntimeException("Invalid updated document: $id");
    $rows[]=['id'=>$id,'revision'=>$rev,'document'=>$row['document']];
    $ops[]=['operationId'=>'benchfix-'.bin2hex(random_bytes(16)),'kind'=>'workouts','id'=>$id,
        'baseRevision'=>$rev,'deleted'=>false,'document'=>$w];
}
foreach($ops as $op)validateOperation($op);
$backup=['operationIds'=>array_column($ops,'operationId'),'createdAt'=>gmdate('c'),'originalRecords'=>$rows,'approvals'=>$plan];
$payload=json_encode($backup,JSON_PRETTY_PRINT|JSON_THROW_ON_ERROR);
writePrivateFile($backupPath,$payload);
echo "Backup created: $backupPath\n";
$results=[];
foreach($ops as $op){
    $result=pushOperationInTransaction($db,$op);
    if($result['conflict'])throw new RuntimeException('Revision conflict. Re-run scan and review approvals.');
    $results[]=$result;
}
$commitStarted=true;
$db->commit();
foreach($results as $result)echo "Updated ".$result['record']['id']." to revision ".$result['record']['revision']."\n";
echo "Done: ".count($ops)." workouts committed atomically. Verify sync on both clients.\n";
}catch(Throwable $e){
    if($db->inTransaction()){try{$db->rollBack();}catch(Throwable $ignored){}}
    if($commitStarted)failMigration('Commit confirmation failed. Preserve the backup and inspect its operation IDs/server revisions before retrying; the batch may already be fully committed.');
    failMigration('Apply aborted before commit; no migration updates committed. '.$e->getMessage());
}
