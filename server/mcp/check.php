<?php
declare(strict_types=1);
if (PHP_SAPI !== 'cli') {http_response_code(404);exit;}
require_once __DIR__.'/config.php';
try {
    $config = mcpConfiguration();
    if ($config === null) {echo "MCP disabled.\n";exit;}
    require_once dirname(__DIR__).'/vendor/autoload.php';
    if (!extension_loaded('openssl') || !extension_loaded('fileinfo')) throw new RuntimeException('Missing extension');
    $token = trim(mcpReadPrivateFile($config['token_file'], 256));
    if (!preg_match('/^[A-Za-z0-9_-]{64}$/D', $token)) throw new RuntimeException('Invalid REST credential file');
    // This checks local configuration only, not the provider or production data.
    echo "MCP configuration, dependencies and local credential file verified. Provider linking still requires an explicit connection test.\n";
} catch (Throwable $e) {
    fwrite(STDERR, "MCP preflight failed. Check dependencies, mcp-config.json, extensions and private credential-file permissions. No secrets were printed.\n");exit(1);
}
