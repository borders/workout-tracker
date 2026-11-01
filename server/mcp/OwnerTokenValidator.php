<?php
declare(strict_types=1);

use Mcp\Server\Transport\Http\OAuth\AuthorizationResult;
use Mcp\Server\Transport\Http\OAuth\AuthorizationTokenValidatorInterface;

final class FieldworkOwnerTokenValidator implements AuthorizationTokenValidatorInterface {
    public function __construct(
        private readonly AuthorizationTokenValidatorInterface $inner,
        private readonly string $ownerSubject,
    ) {}
    public function validate(string $accessToken): AuthorizationResult {
        // No token/header/claim details in errors or logs, including SDK failures.
        try { $result = $this->inner->validate($accessToken); }
        catch (Throwable $e) { return AuthorizationResult::unauthorized('invalid_token'); }
        $token = $result->getAccessToken();
        if (!$result->isAllowed() || $token === null) return AuthorizationResult::unauthorized('invalid_token');
        $subject = $token->getSubject();
        if (!is_string($subject) || !hash_equals($this->ownerSubject, $subject))
            return AuthorizationResult::forbidden('access_denied');
        $issued = $token->getClaim('iat');
        $expires = $token->getClaim('exp');
        if (!is_int($issued) || !is_int($expires) || $issued < 0 || $issued > time() + 15 ||
            $expires <= $issued || $expires - $issued > 3600)
            return AuthorizationResult::unauthorized('invalid_token');
        return $result;
    }
}
