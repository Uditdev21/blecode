from fastapi import HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader
from config import get_settings

# Configures the header name as 'token' for authentication
api_key_header = APIKeyHeader(
    name="token",
    auto_error=False,
    description="Tronn API Key passed as header (e.g., token: your_api_key)",
)


def verify_api_token(token: str = Security(api_key_header)) -> str:
    """
    Validates the API key passed in the 'token' header against the configured API_KEY in .env.
    Raises 401 Unauthorized if missing or incorrect.
    """
    settings = get_settings()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing 'token' authentication header. Please provide 'token: <your_api_key>'.",
        )
    if token != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API token provided.",
        )
    return token

