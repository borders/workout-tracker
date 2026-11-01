<?php
declare(strict_types=1);
require_once __DIR__.'/../../server/api/assistant-security.php';
function check(bool $condition,string $message): void {if(!$condition)throw new RuntimeException($message);}
function denied(callable $action): void {
    try {$action();}catch(Throwable $e){return;}
    throw new RuntimeException('Expected fail-closed exception');
}
$root=sys_get_temp_dir().'/assistant-php-test-'.bin2hex(random_bytes(8));
mkdir($root,0700);putenv('FIELDWORK_PRIVATE_DIR='.$root);
try {
    denied(fn()=>assistantPrivateDirectory());
    $dir=assistantPrivateDirectory(true);
    check((fileperms($dir)&0777)===0700,'Private directory mode');
    check(!assistantAuthenticate('Bearer '.str_repeat('x',64),$dir),'Missing credential');
    $secret=rtrim(strtr(base64_encode(random_bytes(48)),'+/','-_'),'=');
    $file=assistantLockedFile($dir.'/credential.json');
    assistantWriteState($file,['hash'=>hash('sha256',$secret),'expires'=>time()+60]);
    denied(fn()=>assistantAuthenticate('Bearer '.$secret,$dir));
    fclose($file);
    check(assistantAuthenticate('Bearer '.$secret,$dir),'Valid bearer');
    foreach(['Basic '.$secret,'Bearer '.$secret.'extra','Bearer '.str_repeat('0',64),$secret] as $bad)
        check(!assistantAuthenticate($bad,$dir),'Rejected credential');
    $file=assistantLockedFile($dir.'/credential.json');
    assistantWriteState($file,['hash'=>hash('sha256',$secret),'expires'=>time()-1]);fclose($file);
    check(!assistantAuthenticate('Bearer '.$secret,$dir),'Expiry');
    check(assistantRateAllowed($dir,'unit',1),'Initial budget');
    check(!assistantRateAllowed($dir,'unit',1),'Budget exhausted');
    $file=assistantLockedFile($dir.'/rate-unit.json');
    assistantWriteState($file,['window'=>intdiv(time(),60)-1,'count'=>1]);fclose($file);
    check(assistantRateAllowed($dir,'unit',1),'Window reset');
    chmod($dir.'/credential.json',0644);
    denied(fn()=>assistantAuthenticate('Bearer '.$secret,$dir));
    chmod($dir.'/credential.json',0600);
    link($dir.'/credential.json',$dir.'/hardlink');
    denied(fn()=>assistantAuthenticate('Bearer '.$secret,$dir));
    unlink($dir.'/hardlink');
    chmod($dir,0755);denied(fn()=>assistantPrivateDirectory());chmod($dir,0700);
    echo "PASS: PHP private storage, hashed bearer validation, expiry, concurrent lock rejection, window limits/reset, and permission/hardlink failures\n";
} finally {
    foreach(glob($root.'/assistant-private/*')?:[] as $path)unlink($path);
    if(is_dir($root.'/assistant-private'))rmdir($root.'/assistant-private');rmdir($root);
}
