"""JWT authentication utilities for RS256 token verification."""

import jwt
from fastapi import HTTPException, status

from .config import get_settings


def decode_access_token(token: str) -> dict:
    """Decode and verify an RS256-signed JWT using the public key.

    Args:
        token: The encoded JWT string.

    Returns:
        The decoded token payload.

    Raises:
        HTTPException: If the token is expired, invalid, or cannot be decoded.
    """
    settings = get_settings()

    if not settings.jwt_public_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT_PUBLIC_KEY is not configured",
        )

    try:
        payload = jwt.decode(
            token,
            settings.jwt_public_key,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload
