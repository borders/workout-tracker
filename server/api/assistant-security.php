<?php
declare(strict_types=1);

// The shared .fieldwork root may require Apache traversal. Only this dedicated
// directory is owner-only. Never trust proxy-supplied client IP headers.
function assistantPrivateDirectory(bool $create=false): string {
    $root=getenv('FIELDWORK_PRIVATE_DIR')?:dirname(__DIR__,3);
    $dir=$root.'/assistant-private';
    if($create && !file_exists($dir) && !is_link($dir)) {
        $mask=umask(0077);
        try { if(!mkdir($dir,0700) && !is_dir($dir))throw new RuntimeException('Private storage unavailable'); }
        finally {umask($mask);}
    }
    clearstatcache(true,$dir);
    if(is_link($dir)||!is_dir($dir)||(fileperms($dir)&0777)!==0700)
        throw new RuntimeException('Private storage unavailable');
    return $dir;
}
function assistantLockedFile(string $path) {
    clearstatcache(true,$path);
    if(is_link($path))throw new RuntimeException('Unsafe security state');
    $mask=umask(0077);
    try {$file=@fopen($path,'c+b');} finally {umask($mask);}
    if(!$file)throw new RuntimeException('Security state unavailable');
    $stat=fstat($file);
    if(($stat['mode']&0777)!==0600 || ($stat['mode']&0170000)!==0100000 || $stat['nlink']!==1 || $stat['size']>4096 || !flock($file,LOCK_EX|LOCK_NB)) {
        fclose($file);throw new RuntimeException('Security state unavailable');
    }
    return $file;
}
function assistantReadState($file): array {
    rewind($file);$raw=stream_get_contents($file,4097);
    if($raw==='')return [];
    $state=json_decode($raw,true,8,JSON_THROW_ON_ERROR);
    if(!is_array($state))throw new RuntimeException('Invalid security state');
    return $state;
}
function assistantWriteState($file,array $state): void {
    $data=json_encode($state,JSON_THROW_ON_ERROR);
    rewind($file);
    if(!ftruncate($file,0)||fwrite($file,$data)!==strlen($data)||!fflush($file)||!fsync($file))
        throw new RuntimeException('Security state unavailable');
}
function assistantAuthenticate(string $header,string $dir): bool {
    if(strlen($header)>135 || !preg_match('/^Bearer ([A-Za-z0-9_-]{64})$/D',$header,$match))return false;
    $file=assistantLockedFile($dir.'/credential.json');
    try {
        $state=assistantReadState($file);
        return is_string($state['hash']??null) && is_int($state['expires']??null) &&
            $state['expires']>time() && hash_equals($state['hash'],hash('sha256',$match[1]));
    } finally {fclose($file);}
}
// Fixed-size IP slots bound disk usage even under attacker-controlled addresses.
// Failed-auth slots are independent of authenticated read/write budgets.
function assistantRateAllowed(string $dir,string $bucket,int $limit): bool {
    $file=assistantLockedFile($dir.'/rate-'.$bucket.'.json');
    try {
        $state=assistantReadState($file);$window=intdiv(time(),60);
        if(($state['window']??null)!==$window)$state=['window'=>$window,'count'=>0];
        if(!is_int($state['count']??null))throw new RuntimeException('Invalid security state');
        if($state['count']>=$limit)return false;
        $state['count']++;assistantWriteState($file,$state);return true;
    } finally {fclose($file);}
}
