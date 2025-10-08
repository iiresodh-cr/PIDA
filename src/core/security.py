# src/core/security.py
from fastapi import Request, HTTPException, status, Depends
# Importa el logger desde tu configuración para poder registrar mensajes
from src.config import log 

# Excepción en caso de que no se envíe el ID del usuario
credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="User ID header not provided",
    headers={"WWW-Authenticate": "Header"},
)

async def get_current_user_id_insecure(request: Request) -> str:
    """
    FUNCIÓN INSEGURA: Obtiene el ID del usuario directamente del encabezado 'X-User-ID'.
    No realiza ninguna validación. Confía ciegamente en el cliente.
    NO USAR EN PRODUCCIÓN.
    """
    user_id = request.headers.get('X-User-ID')
    
    # LÍNEA DE DEPURACIÓN: Registra el ID y el origen que recibe el servidor.
    # Esto nos dirá exactamente qué está llegando desde cada dominio.
    log.info(f"--- DEBUGGING: Header 'X-User-ID' received: '{user_id}' from origin: {request.headers.get('origin')} ---")
    
    if user_id is None:
        raise credentials_exception
        
    return str(user_id)
