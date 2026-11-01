<?php
declare(strict_types=1);

function mcpPrivateRoot(): string {
    return getenv('FIELDWORK_PRIVATE_DIR') ?: dirname(__DIR__, 3);
}
function mcpTesting(): bool {
    return PHP_SAPI === 'cli-server' && getenv('FIELDWORK_MCP_TESTING') === '1';
}
function mcpReadPrivateFile(string $path, int $maxBytes): string {
    clearstatcache(true, $path);
    if (is_link($path) || !is_file($path)) throw new RuntimeException('Private file unavailable');
    $file = @fopen($path, 'rb');
    if (!$file) throw new RuntimeException('Private file unavailable');
    try {
        $stat = fstat($file);
        if (($stat['mode'] & 0777) !== 0600 || $stat['nlink'] !== 1 || $stat['size'] > $maxBytes)
            throw new RuntimeException('Unsafe private file');
        $data = stream_get_contents($file, $maxBytes + 1);
        if (!is_string($data) || strlen($data) > $maxBytes) throw new RuntimeException('Private file too large');
        return $data;
    } finally { fclose($file); }
}
function mcpOrigin(string $url): string {
    $p = parse_url($url);
    if (!$p || !isset($p['scheme'], $p['host']) || isset($p['user'], $p['pass']) || isset($p['fragment']))
        throw new InvalidArgumentException('Invalid URL');
    $local = mcpTesting() && $p['scheme'] === 'http' && $p['host'] === '127.0.0.1';
    if ($p['scheme'] !== 'https' && !$local) throw new InvalidArgumentException('HTTPS required');
    if (isset($p['query']) || isset($p['user']) || isset($p['pass'])) throw new InvalidArgumentException('Invalid URL');
    return $p['scheme'].'://'.$p['host'].(isset($p['port']) ? ':'.$p['port'] : '');
}
function mcpValidateConfig(array $config): array {
    foreach (['resource', 'issuer', 'owner_subject'] as $key)
        if (!is_string($config[$key] ?? null) || $config[$key] === '') throw new InvalidArgumentException('Incomplete MCP configuration');
    $origin = mcpOrigin($config['resource']);
    mcpOrigin($config['issuer']);
    if (parse_url($config['resource'], PHP_URL_PATH) !== '/workouts/mcp' || strlen($config['owner_subject']) > 256)
        throw new InvalidArgumentException('Invalid MCP configuration');
    $config['metadata_url'] = $origin.'/workouts/.well-known/oauth-protected-resource';
    $config['assistant_url'] = $origin.'/workouts/api/assistant.php';
    // Development has separate single-threaded PHP listeners for MCP and REST.
    // This override is unavailable to every production PHP SAPI.
    if (mcpTesting() && getenv('FIELDWORK_MCP_TEST_ASSISTANT_URL')) {
        $url = getenv('FIELDWORK_MCP_TEST_ASSISTANT_URL');
        mcpOrigin($url);
        if (parse_url($url, PHP_URL_HOST) !== '127.0.0.1' || parse_url($url, PHP_URL_PATH) !== '/workouts/api/assistant.php')
            throw new InvalidArgumentException('Invalid local test backend');
        $config['assistant_url'] = $url;
    }
    $config['token_file'] = mcpPrivateRoot().'/assistant-client-token.txt';
    return $config;
}
function mcpConfiguration(): ?array {
    $path = mcpPrivateRoot().'/mcp-config.json';
    if (!file_exists($path) && !is_link($path)) return null;
    $config = json_decode(mcpReadPrivateFile($path, 8192), true, 16, JSON_THROW_ON_ERROR);
    if (!is_array($config)) throw new RuntimeException('Invalid configuration');
    if (($config['enabled'] ?? false) !== true) return null;
    return mcpValidateConfig($config);
}
function mcpPrivateDirectory(string $child = ''): string {
    // Only fixed internal child names reach this helper.
    $dir = mcpPrivateRoot().'/mcp-private';
    foreach ([$dir, ...($child === '' ? [] : [$dir.'/'.$child])] as $path) {
        if (is_link($path)) throw new RuntimeException('Unsafe MCP storage');
        if (!is_dir($path) && !@mkdir($path, 0700)) throw new RuntimeException('MCP storage unavailable');
        clearstatcache(true, $path);
        if ((fileperms($path) & 0777) !== 0700) throw new RuntimeException('Unsafe MCP storage');
    }
    return $child === '' ? $dir : $dir.'/'.$child;
}
function mcpAuthorizationHeader(): string {
    for ($i = 0; $i <= 10; $i++) {
        $value = $_SERVER[str_repeat('REDIRECT_', $i).'HTTP_AUTHORIZATION'] ?? '';
        if (is_string($value) && $value !== '') return $value;
    }
    return '';
}
