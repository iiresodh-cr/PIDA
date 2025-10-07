# src/core/security.py
from fastapi import Request, HTTPException, status, Depends

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
    
    if user_id is None:
        raise credentials_exception
        
    return str(user_id)
