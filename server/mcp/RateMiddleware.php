<?php
declare(strict_types=1);

use Nyholm\Psr7\Response;
use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;
use Psr\Http\Server\MiddlewareInterface;
use Psr\Http\Server\RequestHandlerInterface;

final class FieldworkMcpRateMiddleware implements MiddlewareInterface {
    public function __construct(private readonly string $directory) {}
    public function process(ServerRequestInterface $request, RequestHandlerInterface $handler): ResponseInterface {
        if ($request->getMethod() !== 'OPTIONS' && !assistantRateAllowed($this->directory, 'owner', 120))
            return new Response(429, ['Retry-After' => (string)(60-time()%60), 'Content-Type' => 'application/json'], '{"error":"Too many requests"}');
        return $handler->handle($request);
    }
}
