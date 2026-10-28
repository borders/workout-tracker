<?php
declare(strict_types=1);
require __DIR__.'/lib.php';
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store, private');
header('X-Content-Type-Options: nosniff');
function respond(int $status,array $body): never {http_response_code($status);echo json_encode($body,JSON_THROW_ON_ERROR);exit;}
$testing=PHP_SAPI==='cli-server'&&getenv('FIELDWORK_TESTING')==='1';
if(!$testing){
    if(($_SERVER['HTTPS']??'')!=='on'&&($_SERVER['HTTPS']??'')!=='1')respond(403,['error'=>'HTTPS is required.']);
    if(!(defined('FIELDWORK_AUTHENTICATED')&&FIELDWORK_AUTHENTICATED===true)&&($_SERVER['REMOTE_USER']??$_SERVER['REDIRECT_REMOTE_USER']??'')!=='fieldwork')respond(401,['error'=>'Sign in with the website username fieldwork.']);
}
try {
    $action=$_GET['action']??'handshake';$method=$_SERVER['REQUEST_METHOD'];
    if(!in_array($action,['handshake','pull','push'],true))respond(404,['error'=>'Unknown API action.']);
    if(($action==='push'&&$method!=='POST')||($action!=='push'&&$method!=='GET'))respond(405,['error'=>'Method not allowed.']);
    session_name('fieldwork_sync');session_set_cookie_params(['path'=>rtrim(dirname($_SERVER['SCRIPT_NAME']),'/').'/','secure'=>!$testing,'httponly'=>true,'samesite'=>'Strict']);
    ini_set('session.use_strict_mode','1');session_start();
    if(!isset($_SESSION['csrf']))$_SESSION['csrf']=bin2hex(random_bytes(32));$csrf=$_SESSION['csrf'];session_write_close();
    if($action==='push'){
        $origin=($testing?'http':'https').'://'.($_SERVER['HTTP_HOST']??'');
        if(($_SERVER['HTTP_ORIGIN']??'')!==$origin||!hash_equals($csrf,$_SERVER['HTTP_X_CSRF_TOKEN']??''))respond(403,['error'=>'Sync authorization expired. Retry sync from this website.']);
        if(!str_starts_with(strtolower($_SERVER['CONTENT_TYPE']??''),'application/json'))respond(415,['error'=>'JSON content type required.']);
        $raw=file_get_contents('php://input',false,null,0,8388609);if(strlen($raw)>8388608)respond(413,['error'=>'Sync request is too large.']);
        $body=json_decode($raw,false,512,JSON_THROW_ON_ERROR);$operations=is_object($body)&&is_array($body->operations??null)?array_map(fn($op)=>is_object($op)?get_object_vars($op):$op,$body->operations):null;
        if(!is_array($operations)||count($operations)<1||count($operations)>25)respond(400,['error'=>'Send between 1 and 25 operations.']);
        foreach($operations as $op)validateOperation($op);
    }
    $db=connect(configuration());
    $meta=$db->query('SELECT instance_id,revision FROM fw_meta WHERE id=1')->fetch(PDO::FETCH_ASSOC);
    if(!$meta)throw new RuntimeException('Sync schema is not initialized.');
    if($action==='handshake')respond(200,['instance'=>$meta['instance_id'],'csrf'=>$csrf]);
    if($action==='pull'){
        $since=filter_var($_GET['since']??0,FILTER_VALIDATE_INT,['options'=>['min_range'=>0]]);if($since===false)respond(400,['error'=>'Invalid cursor.']);
        if($since>(int)$meta['revision'])respond(409,['error'=>'Server revision moved backward; export a backup before reconnecting.']);
        $q=$db->prepare('SELECT kind,id,revision,deleted,document FROM fw_records WHERE revision>? ORDER BY revision LIMIT 501');$q->execute([$since]);$rows=$q->fetchAll(PDO::FETCH_ASSOC);$more=count($rows)>500;if($more)array_pop($rows);
        $records=array_map(fn($r)=>recordFromRow($r['kind'],$r['id'],$r),$rows);$cursor=$records?end($records)['revision']:$since;
        respond(200,['records'=>$records,'cursor'=>$cursor,'more'=>$more]);
    }
    $results=[];foreach($operations as $op)$results[]=pushOperation($db,$op);respond(200,['results'=>$results]);
}catch(InvalidArgumentException|JsonException $e){respond(400,['error'=>$e->getMessage()]);}
catch(PDOException $e){error_log('Fieldwork sync database failure: '.$e->getCode());respond(503,['error'=>'Sync database is unavailable. Check the server configuration; local data is safe.']);}
catch(Throwable $e){error_log('Fieldwork sync error: '.get_class($e));respond(503,['error'=>'Sync is not configured or initialized. Run npm run setup:sync; local data is safe.']);}
