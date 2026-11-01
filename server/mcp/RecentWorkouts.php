<?php
declare(strict_types=1);

use Mcp\Schema\Content\TextContent;
use Mcp\Schema\Result\CallToolResult;

final class FieldworkRecentWorkouts {
    public function __construct(private readonly array $config) {}
    public function recent(int $limit = 5): CallToolResult {
        if ($limit < 1 || $limit > 20) return CallToolResult::error([new TextContent('Limit must be 1–20.')]);
        try {
            $secret = trim(mcpReadPrivateFile($this->config['token_file'], 256));
            if (!preg_match('/^[A-Za-z0-9_-]{64}$/D', $secret)) throw new RuntimeException('Credential unavailable');
            // Fixed method, fixed endpoint, bounded integer query. Model arguments
            // cannot select URLs, methods, credentials or the append action.
            $response = mcpBoundedGet($this->config['assistant_url'].'?action=recent&limit='.$limit,
                ['Authorization' => 'Bearer '.$secret, 'Accept' => 'application/json'], 1048576);
            if ($response->getStatusCode() !== 200) throw new RuntimeException('REST unavailable');
            $body = (string)$response->getBody();
            $data = json_decode($body, false, 64, JSON_THROW_ON_ERROR);
            if (!is_object($data) || !is_array($data->workouts ?? null) || count($data->workouts) > $limit)
                throw new RuntimeException('Unexpected REST response');
            // Retain unknown fields and empty object/array distinctions. Treat
            // workout notes as user data, never as tool instructions.
            return new CallToolResult([new TextContent($body)], structuredContent: $data);
        } catch (Throwable $e) {
            return CallToolResult::error([new TextContent('Fieldwork could not retrieve recent workouts. Nothing was changed. Check the server connection and REST credential privately.')]);
        }
    }
}
