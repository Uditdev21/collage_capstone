import secrets
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader, APIKeyQuery
from app.config import settings

api_key_header = APIKeyHeader(
    name=settings.API_KEY_HEADER,
    auto_error=False,
    description="Header authentication: X-API-Key: <your_key>",
)
api_key_query = APIKeyQuery(
    name="api_key",
    auto_error=False,
    description="Query parameter authentication: ?api_key=<your_key>",
)


async def verify_api_key(
    key_header: str | None = Security(api_key_header),
    key_query: str | None = Security(api_key_query),
) -> str:
    """
    Validates API key from either the 'X-API-Key' header or '?api_key=' query param.
    Uses constant-time comparison (secrets.compare_digest) to prevent timing attacks.
    """
    token = key_header or key_query
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key. Provide it via 'X-API-Key' header or '?api_key=' query parameter.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if not secrets.compare_digest(token, settings.API_KEY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API Key.",
        )

    return token
