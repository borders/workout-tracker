<?php
declare(strict_types=1);
if (PHP_SAPI !== 'cli') {http_response_code(404);exit;}
require_once __DIR__.'/../../server/mcp/config.php';
try {
    if (!getenv('FIELDWORK_PRIVATE_DIR')) throw new RuntimeException('Private root required');
    function mcpPrompt(string $label): string {fwrite(STDOUT, $label);return trim(fgets(STDIN) ?: '');}
    echo "Read-only MCP setup. No secrets are requested, no network requests are made, and no database is accessed.\n";
    $config = ['enabled' => true, 'resource' => 'https://borderseng.com/workouts/mcp',
        'issuer' => mcpPrompt('Exact OAuth issuer URL (including its trailing slash, if any): '),
        'owner_subject' => mcpPrompt('Your immutable OAuth user ID (sub, not email): ')];
    $validated = mcpValidateConfig($config);
    if (strtolower(mcpPrompt('Type enable to create the read-only MCP configuration: ')) !== 'enable') throw new RuntimeException('Cancelled');
    // Never overwrite a prior configuration or follow a symlink. Operator edits
    // for provider/account changes remain explicit and reviewable.
    $mask = umask(0077);
    try {$file = @fopen(mcpPrivateRoot().'/mcp-config.json', 'xb');}finally{umask($mask);}
    if (!$file) throw new RuntimeException('Configuration already exists or root unavailable');
    try {
        $data = json_encode($config, JSON_THROW_ON_ERROR | JSON_PRETTY_PRINT)."\n";
        if (fwrite($file, $data) !== strlen($data) || !fflush($file) || !fsync($file)) throw new RuntimeException('Configuration write failed');
    } finally {fclose($file);}
    echo "Private MCP configuration created. Existing website authentication is unchanged. Deploy only after following docs/MCP.md.\n";
} catch (Throwable $e) {
    fwrite(STDERR, "MCP setup failed or cancelled. Supply a valid HTTPS issuer and user ID, and a private root with no existing mcp-config.json. No credentials were printed.\n");exit(1);
}
