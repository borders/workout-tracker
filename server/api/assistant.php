<?php
declare(strict_types=1);
require_once __DIR__.'/assistant-append.php';
require_once __DIR__.'/assistant-security.php';
// Never render PHP warnings, paths or exception details in API responses.
ini_set('display_errors','0');
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
    $privateRoot=getenv('FIELDWORK_PRIVATE_DIR')?:dirname(__DIR__,3);
    if(!file_exists($privateRoot.'/assistant-private') && !is_link($privateRoot.'/assistant-private')) {
        header('WWW-Authenticate: Bearer');assistantResponse(401,['error'=>'Unauthorized']);
    }
    $dir=assistantPrivateDirectory();
    $auth=$_SERVER['HTTP_AUTHORIZATION']??$_SERVER['REDIRECT_HTTP_AUTHORIZATION']??'';
    if(!assistantAuthenticate($auth,$dir)) {
        $slot=substr(hash('sha256',$_SERVER['REMOTE_ADDR']??'unknown'),0,2);
        if(!assistantRateAllowed($dir,'denied-'.$slot,20)) {
            header('Retry-After: '.(60-time()%60));assistantResponse(429,['error'=>'Too many requests']);
        }
        header('WWW-Authenticate: Bearer');assistantResponse(401,['error'=>'Unauthorized']);
    }
    if(!assistantRateAllowed($dir,'authenticated',120)) {
        header('Retry-After: '.(60-time()%60));assistantResponse(429,['error'=>'Too many requests']);
    }
    $action=$_GET['action']??'';
    $method=$_SERVER['REQUEST_METHOD']??'GET';
    if(!in_array($action,['recent','append_set'],true))assistantResponse(404,['error'=>'Unknown action']);
    if(($action==='recent' && $method!=='GET')||($action==='append_set' && $method!=='POST'))
        {header('Allow: '.($action==='recent'?'GET':'POST'));assistantResponse(405,['error'=>'Method not allowed']);}
    if($action==='recent'){
        $limit=filter_var($_GET['limit']??5,FILTER_VALIDATE_INT,['options'=>['min_range'=>1,'max_range'=>20]]);
        if($limit===false)assistantResponse(400,['error'=>'Invalid limit']);
        $db=connect(configuration());
        // FORCE INDEX fails closed on an unprepared schema; no full-history fallback.
        $query=$db->prepare("SELECT id,revision,document FROM fw_records FORCE INDEX (assistant_recent) WHERE kind='workouts' AND deleted=0 ORDER BY workout_date DESC,id DESC LIMIT ?");
        $query->bindValue(1,$limit,PDO::PARAM_INT);$query->execute();
        $out=[];$bytes=0;
        while($row=$query->fetch(PDO::FETCH_ASSOC)){
            $d=json_decode($row['document'],false,512,JSON_THROW_ON_ERROR);
            $item=['id'=>$row['id'],'date'=>$d->date??'','location'=>$d->location??'',
                'revision'=>(int)$row['revision'],'sets'=>array_slice($d->sets??[],-15)];
            $bytes+=strlen(json_encode($item,JSON_THROW_ON_ERROR));
            if($bytes>1000000)assistantResponse(413,['error'=>'Recent workouts exceed response limit; request a smaller limit']);
            $out[]=$item;
        }
        assistantResponse(200,['workouts'=>$out]);
    }
    if(!assistantRateAllowed($dir,'writes',30)) {header('Retry-After: '.(60-time()%60));assistantResponse(429,['error'=>'Too many requests']);}
    if(strtolower(trim(explode(';',$_SERVER['CONTENT_TYPE']??'')[0]))!=='application/json')
        assistantResponse(415,['error'=>'JSON required']);
    if(isset($_SERVER['CONTENT_LENGTH']) && (float)$_SERVER['CONTENT_LENGTH']>16384)assistantResponse(413,['error'=>'Too large']);
    $raw=file_get_contents('php://input',false,null,0,16385);
    if(strlen($raw)>16384)assistantResponse(413,['error'=>'Too large']);
    try {$data=json_decode($raw,true,32,JSON_THROW_ON_ERROR);}
    catch(JsonException $e){assistantResponse(400,['error'=>'Invalid request']);}
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
    $db=connect(configuration());
    $db->exec('SET SESSION innodb_lock_wait_timeout=5');
    $db->beginTransaction();
    try {
        $result=appendAssistantSetInTransaction($db,$id,$set,'voice-'.$key);
        $db->commit();
    }catch(Throwable $e){if($db->inTransaction())$db->rollBack();throw $e;}
    assistantResponse(200,$result);
}catch(InvalidArgumentException $e){assistantResponse(400,['error'=>'Invalid request']);}
catch(Throwable $e){
    // No exception logging: messages may contain SQL, paths or private content.
    // Operators monitor HTTP status counts without Authorization/body logging.
    assistantResponse(503,['error'=>'Assistant API unavailable']);}
