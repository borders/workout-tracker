<?php
declare(strict_types=1);

use GuzzleHttp\Client;
use GuzzleHttp\Psr7\Request;
use Nyholm\Psr7\Response;
use Psr\Http\Client\ClientInterface;
use Psr\Http\Client\ClientExceptionInterface;
use Psr\Http\Message\RequestInterface;
use Psr\Http\Message\ResponseInterface;

final class McpNetworkFailure extends RuntimeException implements ClientExceptionInterface {}

// Public-key discovery may only contact the configured issuer origin. Never
// follow redirects or token-supplied jku/x5u URLs, nor forward bearer credentials.
final class McpIssuerClient implements ClientInterface {
    public function __construct(private readonly string $issuer) {}
    public function sendRequest(RequestInterface $request): ResponseInterface {
        $url = (string)$request->getUri();
        try {
            if ($request->getMethod() !== 'GET' || mcpOrigin($url) !== mcpOrigin($this->issuer))
                throw new RuntimeException('Untrusted issuer URL');
            return mcpBoundedGet($url, ['Accept' => 'application/json'], 1048576);
        } catch (Throwable $e) { throw new McpNetworkFailure('Issuer unavailable'); }
    }
}
function mcpBoundedGet(string $url, array $headers, int $maxBytes): ResponseInterface {
    $deadline = microtime(true) + 6;
    $client = new Client();
    $response = $client->send(new Request('GET', $url, $headers), [
        'allow_redirects' => false, 'http_errors' => false, 'verify' => true,
        'connect_timeout' => 3, 'timeout' => 6, 'read_timeout' => 2, 'stream' => true,
    ]);
    $stream = $response->getBody();
    try {
        $body = '';
        while (!$stream->eof() && strlen($body) <= $maxBytes) {
            if (microtime(true) > $deadline) throw new RuntimeException('Upstream deadline exceeded');
            $part = $stream->read(min(8192, $maxBytes + 1 - strlen($body)));
            if ($part === '' && !$stream->eof()) throw new RuntimeException('Upstream stalled');
            $body .= $part;
        }
        if (strlen($body) > $maxBytes) throw new RuntimeException('Upstream too large');
        return new Response($response->getStatusCode(), ['Content-Type' => $response->getHeaderLine('Content-Type')], $body);
    } finally { $stream->close(); }
}
