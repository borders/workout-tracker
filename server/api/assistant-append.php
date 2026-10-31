<?php
declare(strict_types=1);
require_once __DIR__.'/lib.php';
// Transaction-only helper. Caller must authenticate and begin/commit the transaction.
function appendAssistantSetInTransaction(PDO $db, string $workoutId, array $set, string $operationId): array {
    if (!$db->inTransaction()) throw new LogicException('Transaction required');
    if (!preg_match('/^[A-Za-z0-9_-]{1,160}$/D',$workoutId) || !preg_match('/^voice-[A-Za-z0-9_-]{12,48}$/D',$operationId)) throw new InvalidArgumentException('Invalid ID');
    $request=json_encode(['id'=>$workoutId,'set'=>$set],JSON_THROW_ON_ERROR);
    $hash=hash('sha256',$request);
    $meta=$db->query('SELECT revision FROM fw_meta WHERE id=1 FOR UPDATE')->fetch(PDO::FETCH_ASSOC);
    if (!$meta) throw new RuntimeException('Missing metadata');
    $q=$db->prepare('SELECT request_hash,response_json FROM fw_operations WHERE id=?');
    $q->execute([$operationId]); $prior=$q->fetch(PDO::FETCH_ASSOC);
    if ($prior) {
        if(!hash_equals($prior['request_hash'],$hash))throw new InvalidArgumentException('Operation ID reused');
        return json_decode($prior['response_json'],true,512,JSON_THROW_ON_ERROR);
    }
    $q=$db->prepare("SELECT revision,deleted,document FROM fw_records WHERE kind='workouts' AND id=? FOR UPDATE");
    $q->execute([$workoutId]);$row=$q->fetch(PDO::FETCH_ASSOC);
    if(!$row || (int)$row['deleted']!==0)throw new InvalidArgumentException('Workout not found');
    $doc=json_decode($row['document'],false,512,JSON_THROW_ON_ERROR);
    if(!is_array($doc->sets??null) || count($doc->sets)>=10000)throw new InvalidArgumentException('Set limit');
    foreach($doc->sets as $old)if(($old->id??null)===($set['id']??null))throw new InvalidArgumentException('Duplicate set ID');
    // Generate times only after the idempotency lookup, so retries retain the
    // committed set and its original logging/completion timestamps.
    $timestamp=gmdate('Y-m-d\TH:i:s\Z');
    $set['loggedAt']=$timestamp;$set['completedAt']=$timestamp;
    $doc->sets[]=$set;$doc->updatedAt=$timestamp;
    if(!validDocument('workouts',$workoutId,$doc))throw new InvalidArgumentException('Invalid workout');
    $body=json_encode($doc,JSON_THROW_ON_ERROR);
    if(strlen($body)>1048576)throw new InvalidArgumentException('Workout too large');
    $revision=(int)$meta['revision']+1;
    $db->exec('UPDATE fw_meta SET revision=revision+1 WHERE id=1');
    $q=$db->prepare("UPDATE fw_records SET revision=?,document=? WHERE kind='workouts' AND id=?");$q->execute([$revision,$body,$workoutId]);
    $receipt=['saved'=>true,'workoutId'=>$workoutId,'revision'=>$revision,'setId'=>$set['id'],'loggedAt'=>$timestamp,'completedAt'=>$timestamp];
    $q=$db->prepare('INSERT INTO fw_operations(id,request_hash,request_json,response_json) VALUES(?,?,?,?)');
    $q->execute([$operationId,$hash,$request,json_encode($receipt,JSON_THROW_ON_ERROR)]);
    return $receipt;
}
