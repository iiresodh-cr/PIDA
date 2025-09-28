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
    history: List[ChatMessage] = []

    # --- CAMPOS REQUERIDOS PARA LA NUEVA LÓGICA ---
    user_id: str = Field(..., description="El ID del usuario de WordPress.")
    conversation_id: Optional[str] = Field(None, description="El ID de la conversación a continuar.")
