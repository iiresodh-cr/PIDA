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
    Decodifica el token JWT para obtener el ID del usuario usando
    autenticación asimétrica (RS256) con una clave pública.
    """
    try:
        # --- INICIO DE LA MODIFICACIÓN PARA RS256 ---
        # Lee la clave pública y el algoritmo desde la configuración.
        public_key = settings.JWT_PUBLIC_KEY
        algorithm = settings.JWT_ALGORITHM

        payload = jwt.decode(
            token,
            public_key,
            algorithms=[algorithm] # Debe ser RS256
        )
        
        # El ID del usuario está en el campo "id" del payload que creamos en WordPress.
        user_id = payload.get("id")
        
        if user_id is None:
            log.warning("Token JWT válido, pero no contiene el ID de usuario.")
            raise credentials_exception
        # --- FIN DE LA MODIFICACIÓN ---
            
        return str(user_id)

    except JWTError as e:
        log.warning(f"Error de validación de JWT: {e}")
        raise credentials_exception
    except Exception as e:
        log.error(f"Error inesperado durante la validación del token: {e}")
        raise credentials_exception
