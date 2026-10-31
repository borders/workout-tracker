<?php
declare(strict_types=1);
require_once __DIR__.'/assistant-append.php';
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store, private');
header('X-Content-Type-Options: nosniff');
function assistantResponse(int $code,array $body): never {
    http_response_code($code);echo json_encode($body,JSON_THROW_ON_ERROR);exit;
}
try{
    $testing=PHP_SAPI==='cli-server' && getenv('FIELDWORK_TESTING')==='1';
    if(!$testing && !in_array($_SERVER['HTTPS']??'', ['on','1'],true))
        assistantResponse(403,['error'=>'HTTPS required']);
    // Dedicated token stored outside the webroot, never the website password.
    $file=(getenv('FIELDWORK_PRIVATE_DIR')?:dirname(__DIR__,3)).'/assistant-token';
    $auth=$_SERVER['HTTP_AUTHORIZATION']??$_SERVER['REDIRECT_HTTP_AUTHORIZATION']??'';
    if(!preg_match('/^Bearer ([A-Za-z0-9_-]{40,128})$/D',$auth,$matches) ||
        !is_file($file) || is_link($file))
        assistantResponse(401,['error'=>'Unauthorized']);
    $secret=trim((string)file_get_contents($file));
    if(strlen($secret)<40 || !hash_equals($secret,$matches[1]))
        assistantResponse(401,['error'=>'Unauthorized']);
    $action=$_GET['action']??'';
    $method=$_SERVER['REQUEST_METHOD']??'GET';
    if(!in_array($action,['recent','append_set'],true))assistantResponse(404,['error'=>'Unknown action']);
    if(($action==='recent' && $method!=='GET')||($action==='append_set' && $method!=='POST'))
        assistantResponse(405,['error'=>'Method not allowed']);
    $db=connect(configuration());
    if($action==='recent'){
        $limit=filter_var($_GET['limit']??5,FILTER_VALIDATE_INT,['options'=>['min_range'=>1,'max_range'=>20]]);
        if($limit===false)assistantResponse(400,['error'=>'Invalid limit']);
        $rows=$db->query("SELECT id,revision,document FROM fw_records WHERE kind='workouts' AND deleted=0")->fetchAll(PDO::FETCH_ASSOC);
        $out=[];
        foreach($rows as $row){
            $d=json_decode($row['document'],false,512,JSON_THROW_ON_ERROR);
            $out[]=['id'=>$row['id'],'date'=>$d->date??'','location'=>$d->location??'',
                'revision'=>(int)$row['revision'],'sets'=>array_slice($d->sets??[],-15)];
        }
        usort($out,static fn($a,$b)=>strcmp($b['date'],$a['date']) ?: strcmp($b['id'],$a['id']));
        assistantResponse(200,['workouts'=>array_slice($out,0,$limit)]);
    }
    if(!str_starts_with(strtolower($_SERVER['CONTENT_TYPE']??''),'application/json'))
        assistantResponse(415,['error'=>'JSON required']);
    $raw=file_get_contents('php://input',false,null,0,16385);
    if(strlen($raw)>16384)assistantResponse(413,['error'=>'Too large']);
    $data=json_decode($raw,true,32,JSON_THROW_ON_ERROR);
    if(!is_array($data))assistantResponse(400,['error'=>'Invalid request']);
    $id=$data['workoutId']??null;$key=$data['idempotencyKey']??null;
    $exercise=$data['exercise']??null;$weight=$data['weight']??null;$reps=$data['reps']??null;
    $notes=$data['notes']??'';$details=$data['details']??[];
    if(!is_string($id)||!preg_match('/^[A-Za-z0-9_-]{1,160}$/D',$id) ||
       !is_string($key)||!preg_match('/^[A-Za-z0-9_-]{12,48}$/D',$key) ||
       !is_string($exercise)||!in_array($exercise,['Barbell bench press','Dumbbell bench press',
       'Decline barbell bench press','Dumbbell overhead press','Leg press','Eagle row','Machine chest press'],true) ||
       (!is_int($weight)&&!is_float($weight))||!is_finite((float)$weight)||$weight<0||$weight>5000||
       (!is_int($reps)&&!is_float($reps))||!is_finite((float)$reps)||$reps<0||$reps>1000||
       !is_string($notes)||strlen($notes)>500||!is_array($details)||
       array_diff(array_keys($details),['pause','buttFlat','feetUp','difficulty']))
        assistantResponse(400,['error'=>'Invalid set']);
    foreach($details as $field=>$value){
        if(in_array($field,['buttFlat','feetUp'],true)&&!is_bool($value))assistantResponse(400,['error'=>'Invalid detail']);
        if(in_array($field,['pause','difficulty'],true)&&(!is_string($value)||strlen($value)>80))
            assistantResponse(400,['error'=>'Invalid detail']);
    }
    // JSON object property order is not part of the meaning of a set.
    ksort($details,SORT_STRING);
    // Deterministic set ID and normalized payload permit equivalent retries.
    $set=['id'=>'voice-'.hash('sha256',$key),'reps'=>$reps,'weight'=>$weight,'exercise'=>$exercise,
          'notes'=>$notes,'raw'=>'','kind'=>'reps','flags'=>[],'details'=>(object)$details];
    $db->beginTransaction();
    try {
        $result=appendAssistantSetInTransaction($db,$id,$set,'voice-'.$key);
        $db->commit();
    }catch(Throwable $e){if($db->inTransaction())$db->rollBack();throw $e;}
    assistantResponse(200,$result);
}catch(InvalidArgumentException|JsonException $e){assistantResponse(400,['error'=>$e->getMessage()]);}
catch(Throwable $e){error_log('Assistant API failure: '.get_class($e));assistantResponse(503,['error'=>'Assistant API unavailable']);}
