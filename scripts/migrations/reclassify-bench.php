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
function readWorkouts(PDO $db): array {
    return $db->query("SELECT id,revision,document FROM fw_records WHERE kind='workouts' AND deleted=0 ORDER BY id")->fetchAll(PDO::FETCH_ASSOC);
}
function candidates(array $rows): array {
    $out=[];
    foreach ($rows as $row) {
        $w=json_decode($row['document'],true,512,JSON_THROW_ON_ERROR);
        if(!str_starts_with($row['id'],'import-'))continue;
        $suspect=[];
        foreach($w['sets']??[] as $s) {
            if(($s['exercise']??'')==='Barbell bench press' && ($s['kind']??'')==='reps'
                && ($s['weight']??999)>=35 && $s['weight']<=100) {
                $suspect[]=['setId'=>$s['id'],'weight'=>$s['weight'],'reps'=>$s['reps'],'notes'=>$s['notes']??''];
            }
        }
        if($suspect)$out[]=['workoutId'=>$row['id'],'revision'=>(int)$row['revision'],
            'date'=>$w['dateLabel']??'', 'location'=>$w['location']??'',
            'sets'=>$suspect,'allSets'=>array_map(static fn($s)=>[
                'id'=>$s['id'],'exercise'=>$s['exercise'],'weight'=>$s['weight'],
                'reps'=>$s['reps'],'notes'=>$s['notes']??''],$w['sets']??[])];
    }
    return $out;
}
if($argc<2 || !in_array($argv[1],['scan','apply'],true))failMigration('Usage: scan [path] | apply approvals.json /absolute/private/backup.json');
$db=connect(configuration());
if($argv[1]==='scan') {
    $result=['warning'=>'Candidates only; NEVER automatic classification. Review complete sessions and original notes.','candidates'=>candidates(readWorkouts($db))];
    $json=json_encode($result,JSON_PRETTY_PRINT|JSON_UNESCAPED_SLASHES|JSON_THROW_ON_ERROR)."\n";
    if(isset($argv[2])) {
        if(file_exists($argv[2]))failMigration('Output exists; refusing overwrite.');
        if(file_put_contents($argv[2],$json,LOCK_EX)===false)failMigration('Could not write report.');
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
$rows=[];$ops=[];$seen=[];
foreach($plan['changes'] as $change) {
    $id=$change['workoutId']??null;$rev=$change['revision']??null;$ids=$change['setIds']??null;
    if(!is_string($id)||!str_starts_with($id,'import-')||!is_int($rev)||!is_array($ids)||!count($ids)||isset($seen[$id]))failMigration('Invalid/duplicate approval entry.');
    $seen[$id]=true;$setIds=array_fill_keys($ids,true);
    if(count($setIds)!==count($ids))failMigration('Duplicate set IDs.');
    $q=$db->prepare("SELECT revision,deleted,document FROM fw_records WHERE kind='workouts' AND id=?");$q->execute([$id]);$row=$q->fetch(PDO::FETCH_ASSOC);
    if(!$row || (int)$row['revision']!==$rev || (int)$row['deleted']!==0)failMigration("Revision changed/missing: $id. Re-run scan.");
    $w=json_decode($row['document'],true,512,JSON_THROW_ON_ERROR);$changed=0;
    foreach($w['sets'] as &$s) if(isset($setIds[$s['id']])) {
        if($s['exercise']!=='Barbell bench press')failMigration("Not a barbell set: $id");
        $s['exercise']='Dumbbell bench press';$changed++;unset($setIds[$s['id']]);
    }
    unset($s);
    if($setIds || $changed!==count($ids))failMigration("Unknown set IDs: $id");
    if(!validDocument('workouts',$id,$w))failMigration("Invalid updated document: $id");
    $rows[]=['id'=>$id,'revision'=>$rev,'document'=>$row['document']];
    $ops[]=['operationId'=>'benchfix-'.bin2hex(random_bytes(16)),'kind'=>'workouts','id'=>$id,
        'baseRevision'=>$rev,'deleted'=>false,'document'=>$w];
}
$backup=['createdAt'=>gmdate('c'),'originalRecords'=>$rows,'approvals'=>$plan];
$handle=@fopen($backupPath,'x');if(!$handle)failMigration('Cannot atomically create backup.');
chmod($backupPath,0600);
$payload=json_encode($backup,JSON_PRETTY_PRINT|JSON_THROW_ON_ERROR);
if(fwrite($handle,$payload)!==strlen($payload)){fclose($handle);failMigration('Backup write incomplete. No writes performed.');}
fflush($handle);fclose($handle);
echo "Backup created: $backupPath\n";
foreach($ops as $op) {
    validateOperation($op);
    $result=pushOperation($db,$op);
    if($result['conflict'])failMigration('Conflict during apply; earlier records may have changed. Do NOT blindly retry. Review backup and re-scan.');
    echo "Updated ".$op['id']." to revision ".$result['record']['revision']."\n";
}
echo "Done: ".count($ops)." workouts updated. Verify sync on both clients.\n";
