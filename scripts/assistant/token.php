<?php
declare(strict_types=1);
if(PHP_SAPI!=='cli'){http_response_code(404);exit;}
require_once __DIR__.'/../../server/api/assistant-security.php';
// No token is accepted on the command line or printed to stdout/stderr.
try {
    $command=$argv[1]??'';
    if(!in_array($command,['provision','rotate','revoke','status'],true))
        throw new RuntimeException('Usage: php scripts/assistant/token.php provision|rotate OUTPUT_FILE [DAYS=30], or revoke|status. Set FIELDWORK_PRIVATE_DIR explicitly.');
    if(!getenv('FIELDWORK_PRIVATE_DIR'))throw new RuntimeException('Set FIELDWORK_PRIVATE_DIR to the private root outside the document root.');
    $dir=assistantPrivateDirectory(true);
    $file=assistantLockedFile($dir.'/credential.json');
    try {
        // Rotation/revocation must also recover a torn/corrupt credential write.
        $state=in_array($command,['rotate','revoke'],true)?[]:assistantReadState($file);
        if($command==='status')echo isset($state['hash'])?'Credential configured; expires '.gmdate('c',$state['expires'])."\n":"No active credential.\n";
        elseif($command==='revoke'){assistantWriteState($file,[]);echo "Credential revoked.\n";}
        else {
            if($command==='provision' && isset($state['hash']))throw new RuntimeException('Credential exists; use rotate.');
            $days=filter_var($argv[3]??30,FILTER_VALIDATE_INT,['options'=>['min_range'=>1,'max_range'=>90]]);
            $output=$argv[2]??'';
            if(!$days || !str_starts_with($output,'/') || is_link($output))throw new RuntimeException('Supply a new absolute output filename and lifetime of 1–90 days.');
            $secret=rtrim(strtr(base64_encode(random_bytes(48)),'+/','-_'),'=');
            $mask=umask(0077);
            try {$out=@fopen($output,'xb');} finally {umask($mask);}
            if(!$out)throw new RuntimeException('Output file must not already exist.');
            try {if(fwrite($out,$secret."\n")!==65 || !fflush($out) || !fsync($out))throw new RuntimeException('Credential output failed');}finally{fclose($out);}
            assistantWriteState($file,['hash'=>hash('sha256',$secret),'expires'=>time()+$days*86400]);
            echo "Credential saved to the owner-only output file. Previous credential is invalid.\n";
        }
    }finally{fclose($file);}
}catch(Throwable $e){fwrite(STDERR,"Credential command failed. Check command arguments and private storage permissions; no credential was printed.\n");exit(1);}
