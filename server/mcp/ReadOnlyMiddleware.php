<?php
declare(strict_types=1);

use Nyholm\Psr7\Response;
use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;
use Psr\Http\Server\MiddlewareInterface;
use Psr\Http\Server\RequestHandlerInterface;

// No stream subscriptions, prompts, resource mutations, tasks, or future SDK
// features may pin a shared-host worker or acquire capabilities accidentally.
final class FieldworkReadOnlyMiddleware implements MiddlewareInterface {
    public function __construct(private readonly ?object $message) {}
    public function process(ServerRequestInterface $request, RequestHandlerInterface $handler): ResponseInterface {
        $method = $this->message->method ?? null;
        if (is_string($method) && !in_array($method, ['initialize', 'notifications/initialized', 'ping', 'tools/list', 'tools/call'], true)) {
            if (!property_exists($this->message, 'id')) return new Response(202);
            $id = $this->message->id;
            if (!is_int($id) && !is_string($id)) $id = null;
            return new Response(200, ['Content-Type' => 'application/json'], json_encode([
                'jsonrpc' => '2.0', 'id' => $id,
                'error' => ['code' => -32601, 'message' => 'Method not available on this read-only endpoint'],
            ], JSON_THROW_ON_ERROR));
        }
        return $handler->handle($request);
    }
}
