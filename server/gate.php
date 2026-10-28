<?php
declare(strict_types=1);
// Every hosted request passes through this gate before static files or the API.
$testing=PHP_SAPI==='cli-server'&&getenv('FIELDWORK_LOGIN_TESTING')==='1';
if(!$testing&&!in_array($_SERVER['HTTPS']??'', ['on','1'],true)){http_response_code(403);exit('HTTPS is required.');}
$private=getenv('FIELDWORK_PRIVATE_DIR')?:dirname(__DIR__,2);
$base='/workouts/';
header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: same-origin');
if(!is_dir($private.'/sessions')&&!mkdir($private.'/sessions',0700,true)){http_response_code(503);exit('Sign-in storage unavailable.');}
ini_set('session.use_strict_mode','1');ini_set('session.gc_maxlifetime','2592000');
session_save_path($private.'/sessions');session_name('fieldwork_login');
session_set_cookie_params(['lifetime'=>2592000,'path'=>$base,'secure'=>!$testing,'httponly'=>true,'samesite'=>'Strict']);session_start();
$path=parse_url($_SERVER['REQUEST_URI'],PHP_URL_PATH)??'';
$relative=str_starts_with($path,$base)?substr($path,strlen($base)):'';
$authenticated=($_SESSION['user']??'')==='fieldwork'&&($_SESSION['expires']??0)>time();
$isPage=in_array($relative,['','index.html','gate.php'],true);
if(!$authenticated){
    header('Cache-Control: no-store, private');header('X-Fieldwork-Login: required');
    if(!$isPage){session_write_close();http_response_code(401);header('Content-Type: application/json');exit('{"error":"Session expired. Reopen the app to sign in."}');}
    $_SESSION['login_csrf']??=bin2hex(random_bytes(32));$error='';
    if(($_SERVER['REQUEST_METHOD']??'GET')==='POST'){
        $valid=hash_equals($_SESSION['login_csrf'],(string)($_POST['csrf']??''));
        $origin=($testing?'http':'https').'://'.($_SERVER['HTTP_HOST']??'');
        if(($_SERVER['HTTP_ORIGIN']??'')!==$origin)$valid=false;
        if(!$valid){session_write_close();http_response_code(403);exit('Sign-in page expired. Reopen the app and try again.');}
        // Limit attempts outside the cookie session so clearing cookies cannot reset it.
        $file=fopen($private.'/login-attempts.json','c+');
        if(!$file||!flock($file,LOCK_EX)){http_response_code(503);exit('Sign-in temporarily unavailable.');}
        $attempts=json_decode(stream_get_contents($file)?:'{}',true)?:[];$now=time();
        foreach($attempts as $key=>$entry)if(($entry['until']??0)<$now)unset($attempts[$key]);
        $key=hash('sha256',$_SERVER['REMOTE_ADDR']??'unknown');$entry=$attempts[$key]??['count'=>0,'until'=>$now+600];
        $hash='';foreach(@file($private.'/htpasswd',FILE_IGNORE_NEW_LINES)?:[] as $line){$parts=explode(':',$line,2);if($parts[0]==='fieldwork')$hash=$parts[1]??'';}
        $success=$entry['count']<10&&$valid&&($_POST['username']??'')==='fieldwork'&&$hash&&password_verify((string)($_POST['password']??''),$hash);
        if($success)unset($attempts[$key]);else{$entry['count']++;$attempts[$key]=$entry;}
        rewind($file);ftruncate($file,0);fwrite($file,json_encode($attempts,JSON_THROW_ON_ERROR));flock($file,LOCK_UN);fclose($file);chmod($private.'/login-attempts.json',0600);
        if($success){session_regenerate_id(true);$_SESSION=['user'=>'fieldwork','expires'=>time()+2592000];session_write_close();header('Location: '.$base,true,303);exit;}
        usleep(250000);$error=$entry['count']>=10?'Too many attempts. Try again in ten minutes.':'Sign-in failed. Check your website username and password.';
    }
    $csrf=htmlspecialchars($_SESSION['login_csrf'],ENT_QUOTES);session_write_close();header('Content-Type: text/html; charset=utf-8');
    ?>
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"><meta name="theme-color" content="#152921"><meta name="apple-mobile-web-app-capable" content="yes"><title>Sign in · Fieldwork</title><style>*{box-sizing:border-box}body{margin:0;background:#f6f5f0;color:#20352b;font:16px system-ui,sans-serif;min-height:100svh;display:grid;place-items:center;padding:24px}main{width:100%;max-width:400px;background:white;border:1px solid #dfe2d7;border-radius:12px;padding:28px}h1{font-size:28px;letter-spacing:-1px}p{font-size:14px;line-height:1.7;color:#6c7869}label{display:block;font-size:14px;margin-top:20px}input,button{font:inherit;width:100%;border-radius:6px;padding:14px;margin-top:8px}input{border:1px solid #ccd5c5}button{background:#294c39;color:white;border:0;margin-top:24px;cursor:pointer}.error{color:#975039}</style></head><body><main><h1>Welcome to Fieldwork.</h1><p>Sign in to your training journal. Use your existing website password, not your SSH password.</p><?php if($error): ?><p role="alert" class="error"><?=htmlspecialchars($error,ENT_QUOTES)?></p><?php endif; ?><form method="post" action="/workouts/"><input type="hidden" name="csrf" value="<?=$csrf?>"><label>Username<input name="username" value="fieldwork" autocomplete="username" required></label><label>Password<input name="password" type="password" autocomplete="current-password" required></label><button type="submit">Sign in</button></form><p>Your sign-in stays on this device for up to 30 days.</p></main></body></html>
<?php exit;
}
session_write_close();
if($relative==='api/sync.php'){session_id('');define('FIELDWORK_AUTHENTICATED',true);$_SERVER['SCRIPT_NAME']=$base.'api/sync.php';require __DIR__.'/api/sync.php';exit;}
if(!in_array($_SERVER['REQUEST_METHOD'],['GET','HEAD'],true)){http_response_code(405);exit;}
if($relative==='')$relative='index.html';
if(!in_array($relative,['index.html','icon.svg','manifest.webmanifest','sw.js'],true)&&!preg_match('~^assets/[A-Za-z0-9_.-]+$~D',$relative)){http_response_code(404);exit;}
$file=realpath(__DIR__.'/'.$relative);
if(!$file||!str_starts_with($file,__DIR__.'/')||!is_file($file)){http_response_code(404);exit;}
$types=['html'=>'text/html; charset=utf-8','js'=>'application/javascript','css'=>'text/css','svg'=>'image/svg+xml','webmanifest'=>'application/manifest+json'];
header('Content-Type: '.($types[pathinfo($file,PATHINFO_EXTENSION)]??'application/octet-stream'));
header('Cache-Control: private, no-cache');
if($_SERVER['REQUEST_METHOD']!=='HEAD')readfile($file);
