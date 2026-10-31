<?php
declare(strict_types=1);
function syncDiagDir(): string { return getenv('FIELDWORK_DIAGNOSTICS_DIR') ?: dirname(__DIR__,3).'/sync-diagnostics'; }
function syncDiagOrigin(): string {
    if(!array_key_exists('HTTP_ORIGIN',$_SERVER))return '[absent]';
    $origin=$_SERVER['HTTP_ORIGIN'];if($origin==='')return '[empty]';if($origin==='null')return 'null';
    // Only a syntactically bare HTTP(S) origin may be recorded. Never retain
    // userinfo, paths, queries, fragments, controls, or arbitrary header strings.
    if(strlen($origin)<=256&&preg_match('~^https?://[A-Za-z0-9.-]+(?::[0-9]{1,5})?$~D',$origin))return $origin;
    return '[invalid/redacted]';
}
function syncDiagEnum(string $name,array $allowed): string {
    if(!array_key_exists($name,$_SERVER))return '[absent]';
    return in_array($_SERVER[$name],$allowed,true)?$_SERVER[$name]:'[other/redacted]';
}
function syncDiagWrite(int $status,?bool $csrfMatch=null): void {
    try {
        $dir=syncDiagDir();$flag=@file_get_contents($dir.'/enabled.json');if($flag===false)return;
        $config=json_decode($flag,true);$now=time();
        if(!is_array($config)||!is_int($config['started']??null)||!is_int($config['expires']??null)||$config['started']>$now||$config['expires']<=$now||$config['expires']>$config['started']+3600)return;
        $action=$_GET['action']??'handshake';if(!in_array($action,['handshake','pull','push'],true))$action='[other]';
        $entry=['time'=>gmdate('c'),'action'=>$action,'status'=>$status,
            'method'=>syncDiagEnum('REQUEST_METHOD',['GET','POST','HEAD']),
            'display_mode'=>syncDiagEnum('HTTP_X_FIELDWORK_DISPLAY_MODE',['standalone','browser']),
            'origin'=>syncDiagOrigin(),
            'sec_fetch_site'=>syncDiagEnum('HTTP_SEC_FETCH_SITE',['same-origin','same-site','cross-site','none']),
            'sec_fetch_mode'=>syncDiagEnum('HTTP_SEC_FETCH_MODE',['cors','no-cors','same-origin','navigate','websocket']),
            'sec_fetch_dest'=>syncDiagEnum('HTTP_SEC_FETCH_DEST',['','document','empty','worker','serviceworker']),
            'login_cookie_present'=>isset($_COOKIE['fieldwork_login']),
            'sync_cookie_present'=>isset($_COOKIE['fieldwork_sync']),
            'csrf_header_present'=>isset($_SERVER['HTTP_X_CSRF_TOKEN']),
            'csrf_matches'=>$csrfMatch];
        // Bound disk use and never let diagnostics block/fail synchronization.
        $old=umask(0077);try{$file=@fopen($dir.'/requests.ndjson','ab');}finally{umask($old);}
        if(!$file)return;
        if(flock($file,LOCK_EX|LOCK_NB)){
            $line=json_encode($entry,JSON_THROW_ON_ERROR)."\n";
            if(fstat($file)['size']+strlen($line)<=262144)fwrite($file,$line);
            flock($file,LOCK_UN);
        }
        fclose($file);
    }catch(Throwable $e){ /* Logging is optional and never changes the response. */ }
}
if(PHP_SAPI==='cli'&&realpath($_SERVER['SCRIPT_FILENAME']??'')===__FILE__){
    $dir=syncDiagDir();$command=$argv[1]??'';
    if($command==='enable'){
        if(!is_dir($dir)&&!mkdir($dir,0700,true)){fwrite(STDERR,"Cannot create diagnostic directory.\n");exit(1);}
        chmod($dir,0700);$old=umask(0077);
        try{file_put_contents($dir.'/requests.ndjson','',LOCK_EX);file_put_contents($dir.'/enabled.json',json_encode(['started'=>time(),'expires'=>time()+3600]),LOCK_EX);}finally{umask($old);}
        chmod($dir.'/requests.ndjson',0600);chmod($dir.'/enabled.json',0600);
        echo "Header-only sync diagnostics enabled for one hour (256 KB maximum). No cookies, tokens, passwords, IPs, user agents, or workout bodies are recorded.\n";
    }elseif($command==='show'){
        if(is_file($dir.'/requests.ndjson'))readfile($dir.'/requests.ndjson');else echo "No diagnostic records.\n";
    }elseif($command==='disable'){
        foreach(['enabled.json','requests.ndjson'] as $file)if(is_file($dir.'/'.$file))unlink($dir.'/'.$file);
        echo "Diagnostics disabled; captured records deleted.\n";
    }else{fwrite(STDERR,"Use enable, show, or disable.\n");exit(1);}
}
