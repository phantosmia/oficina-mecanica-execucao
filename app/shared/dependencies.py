from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.shared.settings import settings

# HTTPBearer em vez do OAuth2PasswordBearer do OS Service: este serviço não
# emite token (não tem /auth/token), só valida o JWT de admin emitido pelo OS
# Service. No Swagger, o botão "Authorize" aceita o token colado direto.
_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> dict[str, str]:
    unauthorized_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciais inválidas.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized_error

    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as error:
        raise unauthorized_error from error

    username = payload.get("sub")
    if username != settings.admin_username:
        raise unauthorized_error

    return {"username": username}
