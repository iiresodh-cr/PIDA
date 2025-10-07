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
    Esta versión es robusta y busca el ID del usuario en múltiples campos
    comunes del payload para maximizar la compatibilidad.
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )

        # Intenta obtener el user_id desde diferentes ubicaciones comunes en el payload
        
        # 1. Busca en la estructura anidada original: payload -> data -> user -> id
        user_id = payload.get("data", {}).get("user", {}).get("id")

        # 2. Si no lo encuentra, busca en el campo 'sub' (estándar de JWT para el ID de sujeto/usuario)
        if user_id is None:
            user_id = payload.get("sub")

        # 3. Si tampoco lo encuentra, busca en un campo 'user_id' en la raíz del payload
        if user_id is None:
            user_id = payload.get("user_id")

        # Si después de todas las comprobaciones, el user_id sigue sin encontrarse, lanza una excepción
        if user_id is None:
            log.error(f"No se pudo encontrar una clave de ID de usuario válida (id, sub, user_id) en el payload del token. Payload recibido: {payload}")
            raise credentials_exception
        
        log.info(f"Token validado correctamente para el user_id: {user_id}")
        return str(user_id)

    except JWTError as e:
        log.error(f"Error de validación de JWT: {e}. El token podría estar malformado, expirado o la clave secreta es incorrecta.")
        raise credentials_exception
    except Exception as e:
        log.error(f"Error inesperado durante la validación del token: {e}")
        raise credentials_exception
