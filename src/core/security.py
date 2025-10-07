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
    Versión de diagnóstico para decodificar el token JWT.
    Registra cada paso y error específico para una depuración detallada.
    """
    if not token:
        log.error("DIAGNÓSTICO: No se recibió ningún token del cliente.")
        raise credentials_exception

    log.info(f"DIAGNÓSTICO: Intentando decodificar token que empieza con: '{token[:15]}...'")

    try:
        # Intenta decodificar el token
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM]
        )
        log.info(f"DIAGNÓSTICO: Token decodificado correctamente. Payload completo: {payload}")

    except JWTError as e:
        # ¡ESTE ES EL LOG MÁS IMPORTANTE!
        log.error(f"DIAGNÓSTICO: ¡FALLO CRÍTICO DE JWT! El error específico es: '{e}'")
        log.error("DIAGNÓSTICO: Esto usualmente significa una de tres cosas:")
        log.error("1. La 'JWT_SECRET_KEY' en Cloud Run es INCORRECTA (el error sería 'Signature verification failed').")
        log.error("2. El token ha EXPIRADO (el error sería 'Expired signature').")
        log.error("3. El algoritmo ('JWT_ALGORITHM') no coincide entre WordPress y el backend.")
        raise credentials_exception
    except Exception as e:
        log.error(f"DIAGNÓSTICO: Ocurrió un error inesperado al decodificar el token: {e}")
        raise credentials_exception

    # Búsqueda del ID de usuario en el payload
    user_id = payload.get("data", {}).get("user", {}).get("id")
    if user_id:
        log.info(f"DIAGNÓSTICO: User ID encontrado en 'data.user.id': {user_id}")
        return str(user_id)

    user_id = payload.get("sub")
    if user_id:
        log.info(f"DIAGNÓSTICO: User ID encontrado en 'sub': {user_id}")
        return str(user_id)

    user_id = payload.get("user_id")
    if user_id:
        log.info(f"DIAGNÓSTICO: User ID encontrado en 'user_id': {user_id}")
        return str(user_id)

    # Si llegamos aquí, la decodificación fue exitosa pero no encontramos el ID
    log.error(f"DIAGNÓSTICO: El token se decodificó bien, pero NO se encontró una clave de ID de usuario válida (id, sub, user_id) en el payload.")
    raise credentials_exception
