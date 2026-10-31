<?php
declare(strict_types=1);
function configPath(): string { return getenv('FIELDWORK_CONFIG') ?: dirname(__DIR__, 3) . '/sync-config.json'; }
function configuration(): array {
    $path = configPath();
    if (!is_file($path)) throw new RuntimeException('Sync database is not configured. Run npm run setup:sync from your computer.');
    $config = json_decode(file_get_contents($path), true, 512, JSON_THROW_ON_ERROR);
    foreach (['host','database','username','password'] as $name) if (!isset($config[$name]) || !is_string($config[$name])) throw new RuntimeException('Invalid server database configuration.');
    if (!preg_match('/^[A-Za-z0-9_.-]+$/', $config['host']) || !preg_match('/^[A-Za-z0-9_]+$/', $config['database'])) throw new RuntimeException('Invalid database host or name.');
    return $config;
}
function connect(array $config): PDO {
    return new PDO((isset($config['socket'])?'mysql:unix_socket='.$config['socket']:'mysql:host='.$config['host']).';dbname='.$config['database'].';charset=utf8mb4', $config['username'], $config['password'], [PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_EMULATE_PREPARES=>false]);
}
function migrate(PDO $db): void {
    $db->exec('CREATE TABLE IF NOT EXISTS fw_meta (id INT PRIMARY KEY, instance_id VARCHAR(64) NOT NULL, revision BIGINT NOT NULL DEFAULT 0) ENGINE=InnoDB');
    $db->exec('CREATE TABLE IF NOT EXISTS fw_records (kind VARCHAR(16) NOT NULL, id VARCHAR(160) NOT NULL, revision BIGINT NOT NULL, deleted TINYINT NOT NULL DEFAULT 0, document LONGTEXT NULL, PRIMARY KEY(kind,id), INDEX(revision)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin');
    $db->exec('CREATE TABLE IF NOT EXISTS fw_operations (id VARCHAR(64) PRIMARY KEY, request_hash CHAR(64) NOT NULL, request_json LONGTEXT NOT NULL, response_json LONGTEXT NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin');
    $query=$db->prepare('INSERT IGNORE INTO fw_meta(id,instance_id,revision) VALUES(1,?,0)');$query->execute([bin2hex(random_bytes(24))]);
}
function validDocument(string $kind, string $id, mixed $doc): bool {
    if(is_object($doc))$doc=json_decode(json_encode($doc,JSON_THROW_ON_ERROR),true,512,JSON_THROW_ON_ERROR);
    if (!is_array($doc) || ($doc['id']??null)!==$id) return false;
    if ($kind==='imports') return is_string($doc['text']??null) && is_string($doc['importedAt']??null);
    foreach(['date','dateLabel','location','notes','raw','updatedAt'] as $field) if(!is_string($doc[$field]??null)) return false;
    if(!is_array($doc['sets']??null)||!is_array($doc['flags']??null)||count($doc['sets'])>10000)return false;
    $ids=[];
    foreach($doc['sets'] as $set){
        if(!is_array($set)||!is_string($set['id']??null)||isset($ids[$set['id']]))return false;
        $ids[$set['id']]=true;
        if(!array_key_exists('reps',$set) || ($set['reps']!==null && (!is_numeric($set['reps']) || !is_int($set['reps'])&&!is_float($set['reps']) || $set['reps']<0)))return false;
        if(!is_int($set['weight']??null)&&!is_float($set['weight']??null))return false;
        if($set['weight']<0 || !in_array($set['kind']??'', ['reps','hold'],true))return false;
        foreach(['exercise','notes','raw'] as $field)if(!is_string($set[$field]??null))return false;
        if(!is_array($set['flags']??null))return false;
    }
    return true;
}
function validateOperation(mixed $op): void {
    if(!is_array($op)||!array_key_exists('document',$op)||!in_array($op['kind']??'', ['workouts','imports'],true)||!is_string($op['id']??null)||!preg_match('/^[A-Za-z0-9_-]{1,160}$/',$op['id'])||!is_string($op['operationId']??null)||!preg_match('/^[A-Za-z0-9_-]{1,64}$/',$op['operationId'])||!is_int($op['baseRevision']??null)||$op['baseRevision']<0||!is_bool($op['deleted']??null))throw new InvalidArgumentException('Invalid sync operation.');
    if($op['deleted'] ? ($op['document']??null)!==null : !validDocument($op['kind'],$op['id'],$op['document']??null))throw new InvalidArgumentException('Invalid sync document.');
    if(strlen(json_encode($op,JSON_THROW_ON_ERROR))>1048576)throw new InvalidArgumentException('One sync record exceeds 1 MB. Export it for review.');
}
function recordFromRow(string $kind,string $id,array|false $row): array {
    return ['kind'=>$kind,'id'=>$id,'revision'=>$row?(int)$row['revision']:0,'deleted'=>$row?(bool)$row['deleted']:true,'document'=>$row&&$row['document']!==null?json_decode($row['document'],false,512,JSON_THROW_ON_ERROR):null];
}
function pushOperation(PDO $db,array $op): array {
    $db->beginTransaction();
    try{
        $result=pushOperationInTransaction($db,$op);
        $db->commit();return $result;
    }catch(Throwable $e){if($db->inTransaction())$db->rollBack();throw $e;}
}
// The caller owns commit/rollback. The shared meta-row lock maintains the same
// revision serialization for ordinary sync and atomic maintenance batches.
function pushOperationInTransaction(PDO $db,array $op): array {
    if(!$db->inTransaction())throw new LogicException('An active transaction is required.');
    $request=json_encode($op,JSON_THROW_ON_ERROR);$hash=hash('sha256',$request);
        // Serialize writes so pull cursors cannot skip a later-committing lower revision.
        $meta=$db->query('SELECT revision FROM fw_meta WHERE id=1 FOR UPDATE')->fetch(PDO::FETCH_ASSOC);
        if(!$meta)throw new RuntimeException('Sync schema is not initialized.');
        $q=$db->prepare('SELECT request_hash,response_json FROM fw_operations WHERE id=?');$q->execute([$op['operationId']]);$prior=$q->fetch(PDO::FETCH_ASSOC);
        if($prior){if(!hash_equals($prior['request_hash'],$hash))throw new InvalidArgumentException('Operation ID was reused with different content.');return (array)json_decode($prior['response_json'],false,512,JSON_THROW_ON_ERROR);}
        $q=$db->prepare('SELECT revision,deleted,document FROM fw_records WHERE kind=? AND id=?');$q->execute([$op['kind'],$op['id']]);$row=$q->fetch(PDO::FETCH_ASSOC);
        $record=recordFromRow($op['kind'],$op['id'],$row);
        if($record['revision']!==$op['baseRevision'])$result=['conflict'=>true,'record'=>$record];
        else{
            $revision=(int)$meta['revision']+1;
            $db->exec('UPDATE fw_meta SET revision=revision+1 WHERE id=1');
            $document=$op['deleted']?null:json_encode($op['document'],JSON_THROW_ON_ERROR);
            $q=$db->prepare('INSERT INTO fw_records(kind,id,revision,deleted,document) VALUES(?,?,?,?,?) ON DUPLICATE KEY UPDATE revision=VALUES(revision),deleted=VALUES(deleted),document=VALUES(document)');$q->execute([$op['kind'],$op['id'],$revision,(int)$op['deleted'],$document]);
            $result=['conflict'=>false,'record'=>['kind'=>$op['kind'],'id'=>$op['id'],'revision'=>$revision,'deleted'=>$op['deleted'],'document'=>$op['document']]];
        }
        // Retain rejected local versions as well as accepted writes for recovery.
        $q=$db->prepare('INSERT INTO fw_operations(id,request_hash,request_json,response_json) VALUES(?,?,?,?)');$q->execute([$op['operationId'],$hash,$request,json_encode($result,JSON_THROW_ON_ERROR)]);
    return $result;
}
