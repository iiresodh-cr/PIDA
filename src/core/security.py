# src/core/security.py

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from src.config import settings, log

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

async def get_current_user_id(token: str = Depends(oauth2_scheme)) -> str:
    """
    Decodifica el token JWT para obtener el ID del usuario.
    MODIFICADO para ser compatible con "Simple JWT Login" y el plugin anterior.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )

        # --- INICIO DE LA MODIFICACIÓN ---
        # Intenta buscar el ID del usuario en varios lugares comunes del payload
        # para dar compatibilidad con diferentes plugins de JWT.
        user_id = payload.get("id") or \
                  payload.get("user_id") or \
                  payload.get("data", {}).get("user", {}).get("id")

        if user_id is None:
            log.warning(f"Token JWT válido, pero no contiene el ID de usuario en las rutas esperadas. Payload: {payload}")
            raise credentials_exception
        # --- FIN DE LA MODIFICACIÓN ---

        return str(user_id)

    except JWTError as e:
        log.warning(f"Error de validación de JWT: {e}")
        raise credentials_exception
    except Exception as e:
        log.error(f"Error inesperado durante la validación del token: {e}")
        raise credentials_exception
