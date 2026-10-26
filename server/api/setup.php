<?php
declare(strict_types=1);
if(PHP_SAPI!=='cli'){http_response_code(404);exit;}
require __DIR__.'/lib.php';
try{
    if(!extension_loaded('pdo_mysql'))throw new RuntimeException('PHP pdo_mysql is required. Select PHP 8.1 or newer with MySQL support.');
    if(in_array('--check',$argv,true)){$db=connect(configuration());$db->query('SELECT instance_id FROM fw_meta WHERE id=1');echo "Sync database connection verified.\n";exit;}
    if(is_file(configPath())){
        echo "Existing configuration found. Verifying connection and applying additive schema setup.\n";
        $config=configuration();
    }else{
        function prompt(string $label): string{echo $label;return trim(fgets(STDIN)?:'');}
        $config=['host'=>prompt('DreamHost MySQL hostname (e.g. mysql.borderseng.com): '),'database'=>prompt('Database name: '),'username'=>prompt('Database username: ')];
        echo 'Database password (hidden): ';$mode=trim((string)shell_exec('stty -g'));if(!$mode)throw new RuntimeException('A terminal is required to enter the password securely.');
        shell_exec('stty -echo');try{$config['password']=rtrim(fgets(STDIN)?:'',"\r\n");}finally{shell_exec('stty '.escapeshellarg($mode));echo "\n";}
        if(!preg_match('/^[A-Za-z0-9_.-]+$/',$config['host'])||!preg_match('/^[A-Za-z0-9_]+$/',$config['database'])||!$config['username']||!$config['password'])throw new RuntimeException('Invalid or empty database settings.');
    }
    $db=connect($config);migrate($db);
    if(!is_file(configPath())){
        $path=configPath();$temp=$path.'.'.bin2hex(random_bytes(8));$old=umask(0077);
        try{if(file_put_contents($temp,json_encode($config,JSON_THROW_ON_ERROR))===false)throw new RuntimeException('Could not write database configuration.');if(!rename($temp,$path))throw new RuntimeException('Could not activate database configuration.');}finally{umask($old);if(is_file($temp))unlink($temp);}
    }
    echo "Sync database configured. Credentials are outside the web directory. Deploy the latest app, then choose Sync now.\n";
}catch(PDOException $e){fwrite(STDERR,"Database connection/setup failed. Verify hostname, database, user privileges, and password in DreamHost. Credentials were not printed.\n");exit(1);}
catch(Throwable $e){fwrite(STDERR,$e->getMessage()."\n");exit(1);}
