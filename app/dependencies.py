import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

bearer_scheme = HTTPBearer()


async def verify_jwt(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    """Verifies a JSON Web Token (JWT) provided via HTTP authorization credentials.

    The function decodes the provided JWT and validates its signature, expiration,
    audience, and issuer information. If the token is valid, the payload is returned.
    """
    token = credentials.credentials

    try:
        payload = jwt.decode(
            token,
            settings.CLIENT_PUBLIC_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
        )
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e

    if payload.get("iss") != settings.JWT_ISSUER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Unknown token issuer"
        )

    return payload
