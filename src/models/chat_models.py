# src/models/chat_models.py

from pydantic import BaseModel, Field
from typing import List, Literal, Optional

class ChatMessage(BaseModel):
    """Representa un único mensaje en el historial de chat."""
    role: Literal["user", "model"]
    content: str

class ChatRequest(BaseModel):
    """El cuerpo de la petición para el endpoint /chat-stream."""
    prompt: str
    # El historial ya no se envía desde el cliente, se obtiene de la DB.
    # Se puede eliminar esta línea si se desea, pero la dejamos para no romper el frontend antiguo.
    history: List[ChatMessage] = []

    # --- NUEVOS CAMPOS ---
    # ID del usuario de WordPress. Es crucial para saber de quién es la conversación.
    user_id: str = Field(..., description="El ID del usuario de WordPress.")
    
    # ID de la conversación actual. Si es None, se creará una nueva.
    conversation_id: Optional[str] = Field(None, description="El ID de la conversación a continuar.")
