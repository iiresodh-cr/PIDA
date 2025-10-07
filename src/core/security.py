# src/core/security.py

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from src.config import settings, log

# Esto le dice a FastAPI que busque un token en el header "Authorization: Bearer <token>"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token") 

# Define una excepción personalizada para credenciales inválidas
credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

async def get_current_user_id(token: str = Depends(oauth2_scheme)) -> str:
    """
    Decodifica el token JWT para obtener el ID del usuario de WordPress.
    Este ID se usará como clave para los documentos en Firestore.
    """
    try:
        # Decodifica el token usando la clave secreta y el algoritmo
        payload = jwt.decode(
            token, 
            settings.JWT_SECRET_KEY, 
            algorithms=[settings.JWT_ALGORITHM]
        )
        
        # Extrae el ID del usuario del payload del token.
        # La estructura 'data.user.id' es la que usa el plugin JWT de WordPress por defecto.
        user_id = payload.get("data", {}).get("user", {}).get("id")
        
        if user_id is None:
            log.warning("Token JWT válido, pero no contiene el ID de usuario.")
            raise credentials_exception
            
        # Devolvemos el ID como string, que es como lo usaremos en Firestore.
        return str(user_id)

    except JWTError as e:
        # Si el token está expirado o es inválido, lanza un error.
        log.warning(f"Error de validación de JWT: {e}")
        raise credentials_exception
    except Exception as e:
        log.error(f"Error inesperado durante la validación del token: {e}")
        raise credentials_exception
